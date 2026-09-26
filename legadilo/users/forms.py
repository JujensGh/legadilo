# SPDX-FileCopyrightText: 2023-2025 Legadilo contributors
#
# SPDX-License-Identifier: AGPL-3.0-or-later

from allauth.account.forms import LoginForm, SignupForm
from allauth.socialaccount.forms import SignupForm as SocialSignupForm
from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, Fieldset, Layout, Submit
from django import forms
from django.contrib.auth import forms as admin_forms
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _

from legadilo.core.forms.widgets import SelectAutocompleteWidget
from legadilo.core.models import Timezone
from legadilo.users import constants
from legadilo.users.models import UserSettings

User = get_user_model()


class UserAdminChangeForm(admin_forms.UserChangeForm):
    class Meta(admin_forms.UserChangeForm.Meta):
        model = User
        field_classes = {"email": forms.EmailField}


class UserAdminCreationForm(admin_forms.UserCreationForm):
    """Form for User Creation in the Admin Area.

    To change user signup, see UserSignupForm and UserSocialSignupForm.
    """

    class Meta(admin_forms.UserCreationForm.Meta):
        model = User
        fields = ("email",)
        field_classes = {"email": forms.EmailField}
        error_messages = {
            "email": {"unique": _("This email has already been taken.")},
        }


class UserLoginForm(LoginForm): ...


class UserSignupForm(SignupForm):
    """Form that will be rendered on a user sign up section/screen.

    Default fields will be added automatically.
    Check UserSocialSignupForm for accounts created from social.
    """

    timezone = forms.ModelChoiceField(
        Timezone.objects.all(),
        required=True,
        widget=SelectAutocompleteWidget(allow_new=False),
        help_text=_("Used to display times and updated feeds at a convenient time."),
    )
    language = forms.ChoiceField(
        label=_("Language"),
        required=False,
        choices=constants.LANGUAGE_CHOICES,
        help_text=_(
            "Set this to force the language of the app. "
            "By default, it will use your browser language. If the "
            "language is not supported, it will fallback to English. "
            "This will also enable you to receive emails in this language."
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.initial["timezone"] = Timezone.objects.get_default()


class UserSocialSignupForm(SocialSignupForm):
    """Renders the form when user has signed up using social accounts.

    Default fields will be added automatically.
    See UserSignupForm otherwise.
    """


class UserSettingsForm(forms.ModelForm):
    timezone = forms.ModelChoiceField(
        Timezone.objects.all(),
        label=_("Timezone"),
        required=True,
        widget=SelectAutocompleteWidget(allow_new=False),
        help_text=_("Used to display times and updated feeds at a convenient time."),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.layout = Layout(
            Fieldset(_("Generic settings"), "default_reading_time", "timezone", "language"),
            Fieldset(
                _("Reading settings"),
                HTML(
                    _(
                        """<p class="text-body-secondary">
The change of these options can be previewed at the bottom of the page.
They impact the fonts and max width for articles details and articles lists.
                        </p>"""
                    )
                ),
                "article_details_font_family",
                "article_details_font_size_desktop",
                "article_details_font_size_tablet",
                "article_details_font_size_mobile",
                "article_details_max_width_desktop",
                "article_details_max_width_tablet",
            ),
            Submit("submit", _("Update")),
        )

    class Meta:
        model = UserSettings
        fields = (
            "default_reading_time",
            "timezone",
            "language",
            "article_details_font_family",
            "article_details_font_size_desktop",
            "article_details_font_size_tablet",
            "article_details_font_size_mobile",
            "article_details_max_width_desktop",
            "article_details_max_width_tablet",
        )
        labels = {
            "default_reading_time": _("Default reading time"),
            "language": _("Language"),
            "article_details_font_family": _("Articles details font"),
            "article_details_font_size_desktop": _("Articles details font size desktop"),
            "article_details_font_size_tablet": _("Articles details font size tablet"),
            "article_details_font_size_mobile": _("Articles details font size mobile"),
            "article_details_max_width_desktop": _("Articles details max width desktop"),
            "article_details_max_width_tablet": _("Articles details max width tablet"),
        }
        help_texts = {
            "language": _(
                "Set this to force the language of the app. "
                "By default, it will use your browser language. If the "
                "language is not supported, it will fallback to English. "
                "This will also enable you to receive emails in this language."
            )
        }
