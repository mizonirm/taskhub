from django import forms
from django.conf import settings
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from .models import User


def _delete_stale_unverified(**lookup):
    """A half-finished signup (never verified) shouldn't block someone retrying."""
    User.objects.filter(is_email_verified=False, is_active=False, **lookup).delete()


class SignupForm(UserCreationForm):
    email = forms.EmailField(required=True, help_text="Use your institutional email address.")
    role = forms.ChoiceField(
        choices=[c for c in User.ROLE_CHOICES if c[0] != "admin"],
        label="I am signing up as",
    )

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email", "role",
                  "password1", "password2"]

    def clean_username(self):
        username = self.cleaned_data["username"]
        _delete_stale_unverified(username__iexact=username)
        return username

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        domains = settings.ALLOWED_EMAIL_DOMAINS
        if domains and email.rsplit("@", 1)[-1] not in domains:
            raise forms.ValidationError(
                "Please use your institutional email (" + ", ".join("@" + d for d in domains) + ")."
            )
        _delete_stale_unverified(email__iexact=email)
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email


class OTPVerifyForm(forms.Form):
    code = forms.CharField(
        max_length=6, min_length=6, label="6-digit code",
        widget=forms.TextInput(attrs={"autofocus": True, "inputmode": "numeric",
                                      "autocomplete": "one-time-code"}),
    )


class LoginForm(AuthenticationForm):
    """Gives clear messages to people who can't log in *yet*, instead of Django's generic error."""

    def clean(self):
        username = self.cleaned_data.get("username")
        password = self.cleaned_data.get("password")
        if username and password:
            user = User.objects.filter(username=username).first()
            if user and not user.is_active and user.check_password(password):
                if user.is_email_verified:
                    raise forms.ValidationError(
                        "Your account is waiting for admin approval. "
                        "You'll be able to log in as soon as it's approved.",
                        code="pending_approval",
                    )
                if self.request is not None:
                    self.request.session["pending_user_id"] = user.id
                raise forms.ValidationError(
                    "Your email isn't verified yet. Use the 'Verify your email' link below "
                    "to enter your code or get a new one.",
                    code="unverified",
                )
        return super().clean()
