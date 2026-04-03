from django.db import models


class State(models.Model):
    state_id = models.IntegerField(primary_key=True, db_column="state_id")
    state_name = models.CharField(max_length=50, db_column="state_name")

    class Meta:
        db_table = "states"
        ordering = ["state_name"]

    def __str__(self) -> str:
        return self.state_name


class LGA(models.Model):
    uniqueid = models.AutoField(primary_key=True, db_column="uniqueid")
    lga_id = models.IntegerField(db_column="lga_id", db_index=True)
    lga_name = models.CharField(max_length=50, db_column="lga_name")
    state_id = models.IntegerField(db_column="state_id", db_index=True)
    lga_description = models.TextField(blank=True, null=True, db_column="lga_description")
    entered_by_user = models.CharField(max_length=50, blank=True, db_column="entered_by_user")
    date_entered = models.DateTimeField(blank=True, null=True, db_column="date_entered")
    user_ip_address = models.CharField(max_length=50, blank=True, db_column="user_ip_address")

    class Meta:
        db_table = "lga"
        ordering = ["lga_name"]

    def __str__(self) -> str:
        return self.lga_name


class Ward(models.Model):
    uniqueid = models.AutoField(primary_key=True, db_column="uniqueid")
    ward_id = models.IntegerField(db_column="ward_id")
    ward_name = models.CharField(max_length=50, db_column="ward_name")
    lga_id = models.IntegerField(db_column="lga_id", db_index=True)
    ward_description = models.TextField(blank=True, null=True, db_column="ward_description")
    entered_by_user = models.CharField(max_length=50, blank=True, db_column="entered_by_user")
    date_entered = models.DateTimeField(blank=True, null=True, db_column="date_entered")
    user_ip_address = models.CharField(max_length=50, blank=True, db_column="user_ip_address")

    class Meta:
        db_table = "ward"
        ordering = ["ward_name"]

    def __str__(self) -> str:
        return self.ward_name


class Party(models.Model):
    id = models.AutoField(primary_key=True, db_column="id")
    partyid = models.CharField(max_length=11, unique=True, db_column="partyid")
    partyname = models.CharField(max_length=11, db_column="partyname")

    class Meta:
        db_table = "party"
        ordering = ["id"]

    def __str__(self) -> str:
        return self.partyname


class SequenceCounter(models.Model):
    name = models.CharField(primary_key=True, max_length=50)
    next_value = models.PositiveIntegerField(default=1)

    class Meta:
        db_table = "sequence_counter"

    def __str__(self) -> str:
        return f"{self.name}: {self.next_value}"


class PollingUnit(models.Model):
    uniqueid = models.AutoField(primary_key=True, db_column="uniqueid")
    polling_unit_id = models.IntegerField(db_column="polling_unit_id")
    ward_id = models.IntegerField(db_column="ward_id", db_index=True)
    lga_id = models.IntegerField(db_column="lga_id", db_index=True)
    uniquewardid = models.IntegerField(blank=True, null=True, db_column="uniquewardid")
    polling_unit_number = models.CharField(
        max_length=50, blank=True, null=True, db_column="polling_unit_number"
    )
    polling_unit_name = models.CharField(
        max_length=50, blank=True, null=True, db_column="polling_unit_name"
    )
    polling_unit_description = models.TextField(
        blank=True, null=True, db_column="polling_unit_description"
    )
    lat = models.CharField(max_length=255, blank=True, null=True, db_column="lat")
    long = models.CharField(max_length=255, blank=True, null=True, db_column="long")
    entered_by_user = models.CharField(
        max_length=50, blank=True, null=True, db_column="entered_by_user"
    )
    date_entered = models.DateTimeField(blank=True, null=True, db_column="date_entered")
    user_ip_address = models.CharField(
        max_length=50, blank=True, null=True, db_column="user_ip_address"
    )

    class Meta:
        db_table = "polling_unit"
        ordering = ["polling_unit_name", "polling_unit_number", "uniqueid"]

    def __str__(self) -> str:
        number = self.polling_unit_number or "No number"
        name = self.polling_unit_name or "Unnamed polling unit"
        return f"{name} ({number})"


class AnnouncedPUResult(models.Model):
    result_id = models.AutoField(primary_key=True, db_column="result_id")
    polling_unit_uniqueid = models.CharField(
        max_length=50, db_column="polling_unit_uniqueid", db_index=True
    )
    party_abbreviation = models.CharField(max_length=4, db_column="party_abbreviation")
    party_score = models.IntegerField(db_column="party_score")
    entered_by_user = models.CharField(max_length=50, blank=True, db_column="entered_by_user")
    date_entered = models.DateTimeField(blank=True, null=True, db_column="date_entered")
    user_ip_address = models.CharField(max_length=50, blank=True, db_column="user_ip_address")

    class Meta:
        db_table = "announced_pu_results"
        ordering = ["polling_unit_uniqueid", "party_abbreviation", "result_id"]


class AnnouncedLGAResult(models.Model):
    result_id = models.AutoField(primary_key=True, db_column="result_id")
    lga_name = models.CharField(max_length=50, db_column="lga_name", db_index=True)
    party_abbreviation = models.CharField(max_length=4, db_column="party_abbreviation")
    party_score = models.IntegerField(db_column="party_score")
    entered_by_user = models.CharField(max_length=50, blank=True, db_column="entered_by_user")
    date_entered = models.DateTimeField(blank=True, null=True, db_column="date_entered")
    user_ip_address = models.CharField(max_length=50, blank=True, db_column="user_ip_address")

    class Meta:
        db_table = "announced_lga_results"
        ordering = ["lga_name", "party_abbreviation", "result_id"]
