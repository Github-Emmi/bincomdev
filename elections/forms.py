from django import forms
from django.db import transaction
from django.utils import timezone

from .models import LGA, AnnouncedPUResult, Party, PollingUnit, Ward
from .services import DELTA_STATE_ID, allocate_next_polling_unit_id
from .source_quirks import normalize_party_code, party_label


class PollingUnitSubmissionForm(forms.Form):
    lga = forms.ModelChoiceField(
        queryset=LGA.objects.filter(state_id=DELTA_STATE_ID).order_by("lga_name"),
        empty_label="Choose an LGA",
        to_field_name="lga_id",
        widget=forms.Select(attrs={"class": "select-input"}),
    )
    ward = forms.ModelChoiceField(
        queryset=Ward.objects.none(),
        empty_label="Choose a ward",
        widget=forms.Select(attrs={"class": "select-input"}),
    )
    polling_unit_number = forms.CharField(
        max_length=50,
        widget=forms.TextInput(attrs={"placeholder": "e.g. DT2205001"}),
    )
    polling_unit_name = forms.CharField(
        max_length=50,
        widget=forms.TextInput(attrs={"placeholder": "e.g. Community Hall, Effurun"}),
    )
    polling_unit_description = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Helpful location notes"}),
    )
    lat = forms.CharField(
        required=False,
        max_length=255,
        widget=forms.TextInput(attrs={"placeholder": "e.g. 5.563128"}),
    )
    long = forms.CharField(
        required=False,
        max_length=255,
        widget=forms.TextInput(attrs={"placeholder": "e.g. 5.782510"}),
    )
    entered_by_user = forms.CharField(
        required=False,
        max_length=50,
        widget=forms.TextInput(attrs={"placeholder": "Your name"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.party_codes = []
        selected_lga_id = self.data.get("lga") if self.is_bound else self.initial.get("lga")

        if selected_lga_id:
            self.fields["ward"].queryset = Ward.objects.filter(lga_id=selected_lga_id).order_by(
                "ward_name"
            )

        for party in Party.objects.order_by("id"):
            code = normalize_party_code(party.partyid)
            if code in self.party_codes:
                continue
            self.party_codes.append(code)
            self.fields[f"party_{code}"] = forms.IntegerField(
                min_value=0,
                label=party_label(code),
                widget=forms.NumberInput(attrs={"placeholder": "0", "min": 0}),
            )

    def clean(self):
        cleaned_data = super().clean()
        lga = cleaned_data.get("lga")
        ward = cleaned_data.get("ward")

        if ward and lga and ward.lga_id != lga.lga_id:
            self.add_error("ward", "Choose a ward that belongs to the selected LGA.")

        return cleaned_data

    def save(self, request):
        lga = self.cleaned_data["lga"]
        ward = self.cleaned_data["ward"]
        with transaction.atomic():
            next_polling_unit_id = allocate_next_polling_unit_id()
            polling_unit = PollingUnit.objects.create(
                polling_unit_id=next_polling_unit_id,
                ward_id=ward.ward_id,
                lga_id=lga.lga_id,
                uniquewardid=ward.uniqueid,
                polling_unit_number=self.cleaned_data["polling_unit_number"],
                polling_unit_name=self.cleaned_data["polling_unit_name"],
                polling_unit_description=self.cleaned_data.get("polling_unit_description") or "",
                lat=self.cleaned_data.get("lat") or "",
                long=self.cleaned_data.get("long") or "",
                entered_by_user=self.cleaned_data.get("entered_by_user") or "Bincom Assessment Candidate",
                date_entered=timezone.now(),
                user_ip_address=self._get_client_ip(request),
            )

            AnnouncedPUResult.objects.bulk_create(
                [
                    AnnouncedPUResult(
                        polling_unit_uniqueid=str(polling_unit.uniqueid),
                        party_abbreviation=code,
                        party_score=self.cleaned_data[f"party_{code}"],
                        entered_by_user=polling_unit.entered_by_user or "",
                        date_entered=timezone.now(),
                        user_ip_address=polling_unit.user_ip_address or "",
                    )
                    for code in self.party_codes
                ]
            )

        return polling_unit

    @staticmethod
    def _get_client_ip(request) -> str:
        forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR", "")
