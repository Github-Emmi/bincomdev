from django.contrib import admin

from .models import AnnouncedLGAResult, AnnouncedPUResult, LGA, Party, PollingUnit, SequenceCounter, State, Ward


@admin.register(State)
class StateAdmin(admin.ModelAdmin):
    list_display = ("state_id", "state_name")
    search_fields = ("state_name",)


@admin.register(LGA)
class LGAAdmin(admin.ModelAdmin):
    list_display = ("lga_id", "lga_name", "state_id")
    list_filter = ("state_id",)
    search_fields = ("lga_name",)


@admin.register(Ward)
class WardAdmin(admin.ModelAdmin):
    list_display = ("uniqueid", "ward_id", "ward_name", "lga_id")
    list_filter = ("lga_id",)
    search_fields = ("ward_name",)


@admin.register(Party)
class PartyAdmin(admin.ModelAdmin):
    list_display = ("partyid", "partyname")
    search_fields = ("partyid", "partyname")


@admin.register(SequenceCounter)
class SequenceCounterAdmin(admin.ModelAdmin):
    list_display = ("name", "next_value")


@admin.register(PollingUnit)
class PollingUnitAdmin(admin.ModelAdmin):
    list_display = ("uniqueid", "polling_unit_number", "polling_unit_name", "ward_id", "lga_id")
    list_filter = ("lga_id",)
    search_fields = ("polling_unit_number", "polling_unit_name")


@admin.register(AnnouncedPUResult)
class AnnouncedPUResultAdmin(admin.ModelAdmin):
    list_display = ("result_id", "polling_unit_uniqueid", "party_abbreviation", "party_score")
    list_filter = ("party_abbreviation",)
    search_fields = ("polling_unit_uniqueid", "entered_by_user")


@admin.register(AnnouncedLGAResult)
class AnnouncedLGAResultAdmin(admin.ModelAdmin):
    list_display = ("result_id", "lga_name", "party_abbreviation", "party_score")
    list_filter = ("party_abbreviation",)
    search_fields = ("lga_name",)
