from django import forms
from django.contrib.auth import password_validation
from django.contrib.auth.forms import AuthenticationForm

from .models import Organization, Product, User

INPUT = "w-full rounded-lg border border-slate-300 px-3 py-2 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-200"


def style(fields):
    for f in fields.values():
        f.widget.attrs.setdefault("class", INPUT)


class SignupForm(forms.Form):
    organization_name = forms.CharField(max_length=200, label="Organization name")
    email = forms.EmailField()
    password1 = forms.CharField(label="Password", widget=forms.PasswordInput)
    password2 = forms.CharField(label="Confirm password", widget=forms.PasswordInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        style(self.fields)
        self.fields["organization_name"].widget.attrs["placeholder"] = "My Test Store"

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(username=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean(self):
        cleaned = super().clean()
        p1, p2 = cleaned.get("password1"), cleaned.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "Passwords do not match.")
        elif p1:
            try:
                password_validation.validate_password(p1, User(username=cleaned.get("email", "")))
            except forms.ValidationError as e:
                self.add_error("password1", e)
        return cleaned


class EmailLoginForm(AuthenticationForm):
    username = forms.EmailField(label="Email", widget=forms.EmailInput(attrs={"autofocus": True}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        style(self.fields)

    def clean_username(self):
        return self.cleaned_data["username"].strip().lower()


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = [
            "name", "sku", "description", "quantity_on_hand",
            "cost_price", "selling_price", "low_stock_threshold",
        ]
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, organization, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = organization
        style(self.fields)

    def clean_sku(self):
        sku = self.cleaned_data["sku"].strip().upper()
        qs = Product.objects.for_org(self.organization).filter(sku=sku)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("A product with this SKU already exists in your organization.")
        return sku


class StockAdjustForm(forms.Form):
    delta = forms.IntegerField(label="+/- units")
    note = forms.CharField(max_length=255, required=False)

    def clean_delta(self):
        delta = self.cleaned_data["delta"]
        if delta == 0:
            raise forms.ValidationError("Enter a non-zero number.")
        return delta


class OrganizationSettingsForm(forms.ModelForm):
    class Meta:
        model = Organization
        fields = ["name", "default_low_stock_threshold"]
        labels = {"name": "Organization name", "default_low_stock_threshold": "Default low stock threshold"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        style(self.fields)
