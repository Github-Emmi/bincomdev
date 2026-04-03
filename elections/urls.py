from django.urls import path

from . import views


app_name = "elections"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("polling-units/", views.polling_unit_results, name="polling-unit-results"),
    path("lga-results/", views.lga_results, name="lga-results"),
    path("polling-units/new/", views.create_polling_unit, name="polling-unit-create"),
    path("api/wards/", views.wards_api, name="wards-api"),
    path("api/polling-units/", views.polling_units_api, name="polling-units-api"),
]
