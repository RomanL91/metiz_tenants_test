from django import forms
from django.forms import modelformset_factory
from .models import Group, GroupTechnicalCardLink


class GroupForm(forms.ModelForm):
    class Meta:
        model = Group
        fields = [
            "id",
            "name",
        ]  # parent/order правим позже; здесь даём быстрое переименование
        widgets = {
            "name": forms.TextInput(
                attrs={"class": "vTextField", "style": "width: 320px"}
            )
        }


GroupFormSet = modelformset_factory(Group, form=GroupForm, extra=0, can_delete=False)


class LinkForm(forms.ModelForm):
    class Meta:
        model = GroupTechnicalCardLink
        fields = ["id", "technical_card_version"]
        widgets = {
            "technical_card_version": forms.Select(attrs={"style": "min-width: 360px"})
        }


LinkFormSet = modelformset_factory(
    GroupTechnicalCardLink, form=LinkForm, extra=0, can_delete=False
)
