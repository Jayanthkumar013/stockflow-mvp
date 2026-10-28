from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q, Sum
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import OrganizationSettingsForm, ProductForm, SignupForm, StockAdjustForm
from .models import Organization, Product, User


def get_org(user):
    """Return the logged-in user's organization (create one for e.g. a superuser without one)."""
    if user.organization_id is None:
        user.organization = Organization.objects.create(name=f"{user.username}'s organization")
        user.save(update_fields=["organization"])
    return user.organization


def org_product_or_404(request, pk):
    # Tenant isolation: a product id from another org simply returns 404.
    return get_object_or_404(Product, pk=pk, organization=get_org(request.user))


# ---------- Auth ----------

def signup(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    form = SignupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        with transaction.atomic():
            org = Organization.objects.create(name=data["organization_name"].strip())
            user = User.objects.create_user(
                username=data["email"], email=data["email"],
                password=data["password1"], organization=org,
            )
        login(request, user)
        messages.success(request, f"Welcome to StockFlow, {org.name}!")
        return redirect("dashboard")
    return render(request, "registration/signup.html", {"form": form})


# ---------- Dashboard ----------

@login_required
def dashboard(request):
    org = get_org(request.user)
    products = Product.objects.for_org(org)
    totals = products.aggregate(total_qty=Coalesce(Sum("quantity_on_hand"), 0))
    low_stock = products.low_stock(org.default_low_stock_threshold).order_by("quantity_on_hand", "name")
    return render(request, "inventory/dashboard.html", {
        "org": org,
        "total_products": products.count(),
        "total_quantity": totals["total_qty"],
        "low_stock": low_stock,
        "low_stock_count": low_stock.count(),
    })


# ---------- Products ----------

@login_required
def product_list(request):
    org = get_org(request.user)
    q = request.GET.get("q", "").strip()
    products = Product.objects.for_org(org).with_stock_status(org.default_low_stock_threshold)
    if q:
        products = products.filter(Q(name__icontains=q) | Q(sku__icontains=q))
    return render(request, "inventory/product_list.html", {
        "products": products, "q": q, "adjust_form": StockAdjustForm(),
    })


@login_required
def product_create(request):
    org = get_org(request.user)
    form = ProductForm(request.POST or None, organization=org)
    if request.method == "POST" and form.is_valid():
        product = form.save(commit=False)
        product.organization = org
        product.last_updated_by = request.user
        product.save()
        messages.success(request, f"Product “{product.name}” created.")
        return redirect("product_list")
    return render(request, "inventory/product_form.html", {"form": form, "is_edit": False})


@login_required
def product_update(request, pk):
    org = get_org(request.user)
    product = org_product_or_404(request, pk)
    form = ProductForm(request.POST or None, instance=product, organization=org)
    if request.method == "POST" and form.is_valid():
        product = form.save(commit=False)
        product.last_updated_by = request.user
        product.save()
        messages.success(request, f"Product “{product.name}” updated.")
        return redirect("product_list")
    return render(request, "inventory/product_form.html", {"form": form, "is_edit": True, "product": product})


@login_required
@require_POST
def product_delete(request, pk):
    product = org_product_or_404(request, pk)
    name = product.name
    product.delete()
    messages.success(request, f"Product “{name}” deleted.")
    return redirect("product_list")


@login_required
@require_POST
def product_adjust(request, pk):
    form = StockAdjustForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Enter a non-zero whole number to adjust stock.")
        return redirect("product_list")
    with transaction.atomic():
        product = get_object_or_404(
            Product.objects.select_for_update(), pk=pk, organization=get_org(request.user)
        )
        new_qty = product.quantity_on_hand + form.cleaned_data["delta"]
        if new_qty < 0:
            messages.error(request, f"Cannot reduce “{product.name}” below 0 (currently {product.quantity_on_hand}).")
            return redirect("product_list")
        product.quantity_on_hand = new_qty
        product.last_stock_note = form.cleaned_data["note"]
        product.last_updated_by = request.user
        product.save()
    messages.success(request, f"Stock for “{product.name}” is now {new_qty}.")
    return redirect(request.POST.get("next") or "product_list")


# ---------- Settings ----------

@login_required
def org_settings(request):
    org = get_org(request.user)
    form = OrganizationSettingsForm(request.POST or None, instance=org)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Settings saved.")
        return redirect("settings")
    return render(request, "inventory/settings.html", {"form": form})
