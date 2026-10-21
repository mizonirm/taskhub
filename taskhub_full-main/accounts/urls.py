from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("health/", views.health, name="health"),
    path("signup/", views.signup, name="signup"),
    path("verify-otp/", views.verify_otp, name="verify_otp"),
    path("verify-otp/resend/", views.resend_otp, name="resend_otp"),
    path("dashboard/", views.dashboard, name="dashboard"),
]
