from django.test import TestCase
from django.urls import reverse

from .models import Organization, Product, User


def make_user(email, org_name):
    org = Organization.objects.create(name=org_name)
    user = User.objects.create_user(username=email, email=email, password="Str0ngPass!word", organization=org)
    return user, org


class SignupTests(TestCase):
    def test_signup_creates_org_and_logs_in(self):
        resp = self.client.post(reverse("signup"), {
            "organization_name": "My Test Store", "email": "Owner@Example.com",
            "password1": "Str0ngPass!word", "password2": "Str0ngPass!word",
        })
        self.assertRedirects(resp, reverse("dashboard"))
        user = User.objects.get(username="owner@example.com")
        self.assertEqual(user.organization.name, "My Test Store")
        self.assertNotEqual(user.password, "Str0ngPass!word")  # stored hashed

    def test_password_mismatch(self):
        resp = self.client.post(reverse("signup"), {
            "organization_name": "X", "email": "a@b.com",
            "password1": "Str0ngPass!word", "password2": "different",
        })
        self.assertContains(resp, "Passwords do not match")
        self.assertFalse(User.objects.exists())

    def test_login_with_email(self):
        make_user("a@b.com", "Org A")
        resp = self.client.post(reverse("login"), {"username": "A@B.com", "password": "Str0ngPass!word"})
        self.assertRedirects(resp, reverse("dashboard"))

    def test_pages_require_login(self):
        for name in ["dashboard", "product_list", "product_create", "settings"]:
            resp = self.client.get(reverse(name))
            self.assertEqual(resp.status_code, 302, name)


class TenantIsolationTests(TestCase):
    def setUp(self):
        self.user_a, self.org_a = make_user("a@a.com", "Org A")
        self.user_b, self.org_b = make_user("b@b.com", "Org B")
        self.product_b = Product.objects.create(organization=self.org_b, name="B secret", sku="B1", quantity_on_hand=3)
        self.client.force_login(self.user_a)

    def test_cannot_see_other_org_products(self):
        resp = self.client.get(reverse("product_list"))
        self.assertNotContains(resp, "B secret")
        resp = self.client.get(reverse("dashboard"))
        self.assertNotContains(resp, "B secret")
        self.assertEqual(resp.context["total_products"], 0)

    def test_cannot_edit_delete_or_adjust_other_org_product(self):
        pk = self.product_b.pk
        self.assertEqual(self.client.get(reverse("product_update", args=[pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("product_delete", args=[pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("product_adjust", args=[pk]), {"delta": 5}).status_code, 404)
        self.product_b.refresh_from_db()
        self.assertEqual(self.product_b.quantity_on_hand, 3)

    def test_same_sku_allowed_in_different_orgs(self):
        resp = self.client.post(reverse("product_create"), {"name": "Mine", "sku": "b1", "quantity_on_hand": 1})
        self.assertRedirects(resp, reverse("product_list"))
        self.assertEqual(Product.objects.get(organization=self.org_a).sku, "B1")


class ProductTests(TestCase):
    def setUp(self):
        self.user, self.org = make_user("a@a.com", "Org A")
        self.client.force_login(self.user)

    def test_create_and_duplicate_sku_rejected(self):
        data = {"name": "Pen", "sku": "PEN-1", "quantity_on_hand": 10, "selling_price": "20.00"}
        self.client.post(reverse("product_create"), data)
        resp = self.client.post(reverse("product_create"), {**data, "sku": "pen-1"})
        self.assertContains(resp, "already exists")
        self.assertEqual(Product.objects.count(), 1)

    def test_update_and_delete(self):
        p = Product.objects.create(organization=self.org, name="Pen", sku="P1", quantity_on_hand=1)
        self.client.post(reverse("product_update", args=[p.pk]), {"name": "Pen 2", "sku": "P1", "quantity_on_hand": 50})
        p.refresh_from_db()
        self.assertEqual((p.name, p.quantity_on_hand, p.last_updated_by), ("Pen 2", 50, self.user))
        self.assertEqual(self.client.get(reverse("product_delete", args=[p.pk])).status_code, 405)  # POST only
        self.client.post(reverse("product_delete", args=[p.pk]))
        self.assertFalse(Product.objects.exists())

    def test_adjust_stock(self):
        p = Product.objects.create(organization=self.org, name="Pen", sku="P1", quantity_on_hand=10)
        self.client.post(reverse("product_adjust", args=[p.pk]), {"delta": -4, "note": "sold"})
        p.refresh_from_db()
        self.assertEqual((p.quantity_on_hand, p.last_stock_note), (6, "sold"))
        self.client.post(reverse("product_adjust", args=[p.pk]), {"delta": -100})
        p.refresh_from_db()
        self.assertEqual(p.quantity_on_hand, 6)  # never below zero

    def test_negative_quantity_rejected(self):
        resp = self.client.post(reverse("product_create"), {"name": "X", "sku": "X", "quantity_on_hand": -1})
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Product.objects.exists())

    def test_search(self):
        Product.objects.create(organization=self.org, name="Blue Pen", sku="BP1")
        Product.objects.create(organization=self.org, name="Notebook", sku="NB1")
        resp = self.client.get(reverse("product_list"), {"q": "nb"})
        self.assertContains(resp, "Notebook")
        self.assertNotContains(resp, "Blue Pen")


class DashboardTests(TestCase):
    def setUp(self):
        self.user, self.org = make_user("a@a.com", "Org A")
        self.client.force_login(self.user)
        Product.objects.create(organization=self.org, name="Low own", sku="L1", quantity_on_hand=2, low_stock_threshold=3)
        Product.objects.create(organization=self.org, name="Low default", sku="L2", quantity_on_hand=5)  # default 5
        Product.objects.create(organization=self.org, name="Fine", sku="F1", quantity_on_hand=100)

    def test_summary_and_low_stock(self):
        resp = self.client.get(reverse("dashboard"))
        self.assertEqual(resp.context["total_products"], 3)
        self.assertEqual(resp.context["total_quantity"], 107)
        names = [p.name for p in resp.context["low_stock"]]
        self.assertEqual(sorted(names), ["Low default", "Low own"])

    def test_default_threshold_setting_changes_low_stock(self):
        self.client.post(reverse("settings"), {"name": "Org A", "default_low_stock_threshold": 1})
        resp = self.client.get(reverse("dashboard"))
        self.assertEqual([p.name for p in resp.context["low_stock"]], ["Low own"])
