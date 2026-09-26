# SPDX-FileCopyrightText: 2023-2025 Legadilo contributors
#
# SPDX-License-Identifier: AGPL-3.0-or-later
from allauth.account.decorators import reauthentication_required
from allauth.account.internal.flows.logout import logout
from allauth.account.views import LoginView as AccountLoginView
from allauth.account.views import LogoutView as AccountLogoutView
from allauth.account.views import SignupView as AccountSignupView
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils import translation
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods
from django.views.generic import RedirectView, UpdateView

from legadilo.core.utils.locale import enforce_language_on_response, stop_enforcing_language
from legadilo.users.forms import UserSettingsForm
from legadilo.users.models import UserSettings

User = get_user_model()


class UserSignupView(AccountSignupView):
    def form_valid(self, form):
        resp = super().form_valid(form)
        enforce_language_on_response(resp, form.cleaned_data.get("language"))
        return resp


signup_view = UserSignupView.as_view()


class UserLoginView(AccountLoginView): ...


user_login_view = UserLoginView.as_view()


class UserUpdateView(LoginRequiredMixin, SuccessMessageMixin, UpdateView):
    model = User
    fields = ["name"]
    success_message = _("Information successfully updated")

    def get_success_url(self):
        # for mypy to know that the user is authenticated
        assert self.request.user.is_authenticated  # ruff:ignore[assert]
        return self.request.user.get_absolute_url()

    def get_object(self, queryset=None):
        return self.request.user


user_update_view = UserUpdateView.as_view()


class UserRedirectView(LoginRequiredMixin, RedirectView):
    permanent = False

    def get_redirect_url(self):
        return reverse("reading:default_reading_list")


user_redirect_view = UserRedirectView.as_view()


@require_http_methods(["GET", "POST"])
@login_required
def user_update_settings_view(request):
    user_settings = UserSettings.objects.get(user=request.user)
    form = UserSettingsForm(instance=user_settings)
    if request.method == "POST":
        form = UserSettingsForm(request.POST, instance=user_settings)
        if form.is_valid():
            user_settings = form.save()
            translation.activate(user_settings.language)
            messages.success(request, _("Settings correctly updated"))
            # To update current settings and display the article details preview correctly
            # after a save.
            request.user.settings = user_settings
        else:
            messages.error(request, _("Failed to update settings"))

    response = TemplateResponse(
        request,
        "users/user_settings.html",
        {
            "form": form,
            "user": request.user,
        },
    )
    enforce_language_on_response(response, user_settings.language)
    return response


@require_http_methods(["POST"])
@reauthentication_required
def delete_account_view(request):
    request.user.delete()
    messages.success(request, _("Account deleted successfully"))
    logout(request, show_message=False)
    return redirect("website:home")


class LogoutView(AccountLogoutView):
    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        stop_enforcing_language(response)
        return response


logout_view = LogoutView.as_view()
