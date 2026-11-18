import json
import shutil
import tempfile
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Expense, Trip, TripCollaborator
from .views import _financial_summary

# Cloudinary is never touched in tests: media goes to a throw-away folder.
_TMP = tempfile.mkdtemp()
_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
# 1x1 GIF
_GIF = (b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,"
        b"\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;")


def _img(name="p.gif"):
    return SimpleUploadedFile(name, _GIF, content_type="image/gif")


@override_settings(STORAGES=_STORAGES, MEDIA_ROOT=_TMP, ALLOWED_HOSTS=["testserver"], SECURE_SSL_REDIRECT=False)
class TravelMemoriesTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(_TMP, ignore_errors=True)

    def setUp(self):
        self.owner = User.objects.create_user("owner", password="pw")
        self.viewer = User.objects.create_user("viewer", password="pw")
        self.editor = User.objects.create_user("editor", password="pw")
        self.stranger = User.objects.create_user("stranger", password="pw")
        t = date.today()
        self.goa = self._trip("Goa Trip", "Goa", t - timedelta(days=40), t - timedelta(days=36), 10000)
        self.manali = self._trip("Manali", "manali", t - timedelta(days=100), t - timedelta(days=95), 0)
        self.ongoing = self._trip("Now", "Paris", t - timedelta(days=1), t + timedelta(days=3), 500)
        TripCollaborator.objects.create(trip=self.goa, user=self.viewer, permission="view")
        TripCollaborator.objects.create(trip=self.goa, user=self.editor, permission="edit")

    def _trip(self, name, dest, s, e, budget, owner=None):
        return Trip.objects.create(name=name, destination=dest, start_date=s, end_date=e,
                                   budget=budget, created_by=owner or self.owner,
                                   participants=json.dumps(["A", "B", "C"]))

    def _exp(self, trip, amount, **kw):
        return Expense.objects.create(trip=trip, title="x", amount=amount, paid_by="A", **kw)

    # ── access ────────────────────────────────────────────────────────────
    def test_login_required(self):
        r = self.client.get(reverse("trip_list"))
        self.assertEqual(r.status_code, 302)
        self.assertIn("login", r.url)

    def test_only_accessible_completed_trips(self):
        self.client.login(username="owner", password="pw")
        names = {c["trip"].name for c in self.client.get(reverse("trip_list")).context["cards"]}
        self.assertEqual(names, {"Goa Trip", "Manali"})            # ongoing excluded

        self.client.login(username="viewer", password="pw")
        names = {c["trip"].name for c in self.client.get(reverse("trip_list")).context["cards"]}
        self.assertEqual(names, {"Goa Trip"})                      # shared only

        self.client.login(username="stranger", password="pw")
        self.assertEqual(self.client.get(reverse("trip_list")).context["cards"], [])

    # ── stats + money ─────────────────────────────────────────────────────
    def test_header_stats_dynamic(self):
        self._exp(self.goa, "1200.50")
        self._exp(self.manali, "300")
        self._trip("Goa again", "GOA ", date.today() - timedelta(days=300),
                   date.today() - timedelta(days=299), 100)
        self.client.login(username="owner", password="pw")
        s = self.client.get(reverse("trip_list")).context["stats"]
        self.assertEqual(s["trips"], 3)
        self.assertEqual(s["spent"], Decimal("1500.50"))
        self.assertEqual(s["destinations"], 2)                     # goa/GOA/manali -> 2
        self.assertEqual(s["days"], 5 + 6 + 2)                     # inclusive day counts

    def test_spend_not_multiplied_by_collaborators(self):
        self._exp(self.goa, "1000")                                # goa has 2 collaborators
        self.client.login(username="owner", password="pw")
        card = [c for c in self.client.get(reverse("trip_list")).context["cards"]
                if c["trip"].id == self.goa.id][0]
        self.assertEqual(card["fin"]["spent"], Decimal("1000"))

    def test_financial_summary_edge_cases(self):
        f = _financial_summary(10000, 2500)
        self.assertEqual((f["remaining"], f["pct"], f["state"]), (Decimal("7500"), 25.0, "good"))
        f = _financial_summary(1000, 1500)                         # overspent
        self.assertEqual(f["remaining"], Decimal(0))               # never negative
        self.assertEqual(f["overspent_by"], Decimal("500"))
        self.assertEqual((f["pct"], f["bar_pct"], f["state"]), (150.0, 100, "over"))
        f = _financial_summary(0, 300)                             # zero budget
        self.assertIsNone(f["pct"]); self.assertIsNone(f["remaining"]); self.assertEqual(f["state"], "nobudget")
        f = _financial_summary(None, 0)                            # missing budget, no spend
        self.assertTrue(f["no_expenses"]); self.assertEqual(f["state"], "nobudget")
        f = _financial_summary(1000, 900)
        self.assertEqual(f["state"], "warn")

    def test_overspent_page_never_shows_negative(self):
        self._exp(self.goa, "12500")
        self.client.login(username="owner", password="pw")
        html = self.client.get(reverse("trip_list")).content.decode()
        self.assertIn("Over by ₹2,500", html)
        self.assertNotIn("₹-", html)
        self.assertIn("125.0% of budget used", html)

    def test_no_budget_card(self):
        self.client.login(username="owner", password="pw")
        html = self.client.get(reverse("trip_list")).content.decode()
        self.assertIn("Not set", html)
        self.assertIn("No budget set", html)

    # ── cover photo ───────────────────────────────────────────────────────
    def _cover(self, user="owner"):
        self.client.login(username=user, password="pw")
        return [c for c in self.client.get(reverse("trip_list")).context["cards"]
                if c["trip"].id == self.goa.id][0]

    def test_cover_auto_then_custom_then_reset(self):
        self.assertIsNone(self._cover()["cover_url"])              # fallback
        self._exp(self.goa, 10, receipt=_img("bill.gif"), receipt_type="bill")
        self.assertIsNone(self._cover()["cover_url"])              # bills aren't auto-covers
        first = self._exp(self.goa, 10, receipt=_img("a.gif"), receipt_type="photo")
        second = self._exp(self.goa, 10, receipt=_img("b.gif"), receipt_type="photo")
        self.assertIn(first.receipt.name.split("/")[-1].split(".")[0], self._cover()["cover_url"])

        url = reverse("trip_cover", args=[self.goa.id])
        r = self.client.post(url, {"action": "set", "expense_id": second.id})
        self.assertTrue(r.json()["ok"])
        card = self._cover()
        self.assertTrue(card["has_custom_cover"])
        self.assertIn(second.receipt.name.split("/")[-1].split(".")[0], card["cover_url"])

        r = self.client.post(url, {"action": "reset"})
        self.assertTrue(r.json()["ok"])
        self.assertFalse(self._cover()["has_custom_cover"])

    def test_cover_permissions(self):
        e = self._exp(self.goa, 10, receipt=_img(), receipt_type="photo")
        url = reverse("trip_cover", args=[self.goa.id])
        self.client.login(username="viewer", password="pw")
        self.assertEqual(self.client.post(url, {"action": "set", "expense_id": e.id}).status_code, 403)
        self.assertTrue(self.client.get(url).json()["ok"])         # may look
        self.assertFalse(self.client.get(url).json()["can_edit"])
        self.client.login(username="editor", password="pw")
        self.assertTrue(self.client.post(url, {"action": "set", "expense_id": e.id}).json()["ok"])
        self.client.login(username="stranger", password="pw")
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(url, {"action": "reset"}).status_code, 403)

    def test_cannot_use_another_trips_image(self):
        other = self._exp(self.manali, 5, receipt=_img(), receipt_type="photo")
        self.client.login(username="owner", password="pw")
        r = self.client.post(reverse("trip_cover", args=[self.goa.id]), {"action": "set", "expense_id": other.id})
        self.assertEqual(r.status_code, 400)
        self.goa.refresh_from_db()
        self.assertIsNone(self.goa.cover_expense_id)

    def test_deleting_cover_expense_resets_cover(self):
        e = self._exp(self.goa, 10, receipt=_img(), receipt_type="photo")
        self.goa.cover_expense = e; self.goa.save()
        e.delete()
        self.goa.refresh_from_db()
        self.assertIsNone(self.goa.cover_expense_id)
        self.assertEqual(Trip.objects.filter(id=self.goa.id).count(), 1)   # trip untouched

    def test_edit_button_only_for_editors(self):
        self.client.login(username="viewer", password="pw")
        self.assertNotIn("openCover(", self.client.get(reverse("trip_list")).content.decode().split("<script>")[0])
        self.client.login(username="editor", password="pw")
        self.assertIn("openCover(", self.client.get(reverse("trip_list")).content.decode())

    # ── pages ─────────────────────────────────────────────────────────────
    def test_empty_state(self):
        self.client.login(username="stranger", password="pw")
        html = self.client.get(reverse("trip_list")).content.decode()
        self.assertIn("Your travel memories are waiting to be created.", html)
        self.assertIn(reverse("make_trip"), html)

    def test_action_links_use_existing_urls(self):
        self.client.login(username="owner", password="pw")
        html = self.client.get(reverse("trip_list")).content.decode()
        for name in ("trip_dashboard", "view_expenses", "spending_heatmap", "settlement",
                     "trip_photos_videos", "export_expenses_pdf"):
            self.assertIn(reverse(name, args=[self.goa.id]), html)

    def test_trip_history_unchanged(self):
        self.client.login(username="owner", password="pw")
        r = self.client.get(reverse("trip_history"))
        self.assertEqual(r.status_code, 200)
        self.assertTemplateUsed(r, "trip/trip_history.html")
        self.assertNotIn("Your Travel Memories", r.content.decode())
        self.assertEqual({t.name for t in r.context["trips"]}, {"Goa Trip", "Manali", "Now"})

    def test_existing_pages_still_render(self):
        self._exp(self.goa, 100)
        self.client.login(username="owner", password="pw")
        for name in ("trip_dashboard", "view_expenses", "settlement", "trip_photos_videos"):
            self.assertEqual(self.client.get(reverse(name, args=[self.goa.id])).status_code, 200, name)
