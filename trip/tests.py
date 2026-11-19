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

    # ── cover photo (uploaded by the trip creator, never an expense photo) ──
    @staticmethod
    def _png(name="cover.png", size=(60, 40)):
        from io import BytesIO
        from PIL import Image
        buf = BytesIO()
        Image.new("RGB", size, (200, 80, 80)).save(buf, "PNG")
        return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")

    def _card(self, user="owner"):
        self.client.login(username=user, password="pw")
        return [c for c in self.client.get(reverse("trip_list")).context["cards"]
                if c["trip"].id == self.goa.id][0]

    def test_expense_photos_never_become_the_cover(self):
        self._exp(self.goa, 10, receipt=_img("a.gif"), receipt_type="photo")
        self._exp(self.goa, 10, receipt=_img("b.gif"), receipt_type="bill")
        card = self._card()
        self.assertIsNone(card["cover_url"])
        self.assertFalse(card["has_custom_cover"])

    def test_owner_can_upload_adjust_and_remove_cover(self):
        url = reverse("trip_cover", args=[self.goa.id])
        self.client.login(username="owner", password="pw")
        r = self.client.post(url, {"action": "upload", "image": self._png(), "pos_x": "30", "pos_y": "70", "zoom": "1.8"})
        self.assertTrue(r.json()["ok"], r.content)
        self.goa.refresh_from_db()
        self.assertTrue(self.goa.cover_image)
        self.assertEqual((self.goa.cover_pos_x, self.goa.cover_pos_y, self.goa.cover_zoom), (30.0, 70.0, 1.8))
        card = self._card()
        self.assertTrue(card["has_custom_cover"])
        self.assertIn("covers/", card["cover_url"])
        self.assertIn("object-position:30.00% 70.00%", self.goa.cover_style)

        # adjust only — values are clamped
        r = self.client.post(url, {"action": "adjust", "pos_x": "250", "pos_y": "-5", "zoom": "9"})
        self.assertTrue(r.json()["ok"])
        self.goa.refresh_from_db()
        self.assertEqual((self.goa.cover_pos_x, self.goa.cover_pos_y, self.goa.cover_zoom), (100.0, 0.0, 3.0))

        # replacing swaps the file; removing clears everything
        old = self.goa.cover_image.name
        self.client.post(url, {"action": "upload", "image": self._png("second.png")})
        self.goa.refresh_from_db()
        self.assertNotEqual(self.goa.cover_image.name, old)
        r = self.client.post(url, {"action": "remove"})
        self.assertTrue(r.json()["ok"])
        self.goa.refresh_from_db()
        self.assertFalse(self.goa.cover_image)
        self.assertEqual((self.goa.cover_pos_x, self.goa.cover_pos_y, self.goa.cover_zoom), (50.0, 50.0, 1.0))

    def test_only_the_creator_can_change_the_cover(self):
        url = reverse("trip_cover", args=[self.goa.id])
        for who in ("viewer", "editor", "stranger"):       # even editors can't
            self.client.login(username=who, password="pw")
            r = self.client.post(url, {"action": "upload", "image": self._png()})
            self.assertEqual(r.status_code, 403, who)
        self.goa.refresh_from_db()
        self.assertFalse(self.goa.cover_image)
        self.client.login(username="viewer", password="pw")
        self.assertFalse(self.client.get(url).json()["can_manage"])     # may look, not change
        self.client.login(username="stranger", password="pw")
        self.assertEqual(self.client.get(url).status_code, 403)
        su = User.objects.create_superuser("root", password="pw")
        self.client.login(username="root", password="pw")
        self.assertTrue(self.client.post(url, {"action": "upload", "image": self._png()}).json()["ok"])

    def test_cover_rejects_bad_files(self):
        url = reverse("trip_cover", args=[self.goa.id])
        self.client.login(username="owner", password="pw")
        junk = SimpleUploadedFile("x.png", b"not an image", content_type="image/png")
        self.assertEqual(self.client.post(url, {"action": "upload", "image": junk}).status_code, 400)
        self.assertEqual(self.client.post(url, {"action": "upload", "image": _img()}).status_code, 400)  # GIF
        self.assertEqual(self.client.post(url, {"action": "upload"}).status_code, 400)
        self.assertEqual(self.client.post(url, {"action": "adjust", "zoom": "2"}).status_code, 400)       # no cover yet
        self.assertEqual(self.client.post(url, {"action": "nope"}).status_code, 400)

    def test_cover_button_only_for_the_creator(self):
        self.client.login(username="editor", password="pw")
        html = self.client.get(reverse("trip_list")).content.decode()
        self.assertNotIn('onclick="openCover(', html)
        self.assertNotIn("cvm-frame", html)
        self.client.login(username="owner", password="pw")
        html = self.client.get(reverse("trip_list")).content.decode()
        self.assertIn('onclick="openCover(', html)
        self.assertIn("cvm-frame", html)

    # ── 3D hero ───────────────────────────────────────────────────────────
    def test_3d_ring_has_a_postcard_per_trip_and_pads_to_six(self):
        self.client.login(username="owner", password="pw")
        r = self.client.get(reverse("trip_list"))
        html = r.content.decode()
        self.assertEqual(r.context["ring_n"], 6)
        self.assertEqual(html.count('class="face"'), 2)             # Goa + Manali
        self.assertEqual(html.count('class="face pad"'), 4)
        self.assertIn('href="#tc-%d"' % self.goa.id, html)

    # ── memories page + drive links ───────────────────────────────────────
    def _links_url(self):
        return reverse("memory_links_save", args=[self.goa.id])

    def test_editor_saves_drive_links_and_page_shows_them(self):
        self.client.login(username="editor", password="pw")
        r = self.client.post(self._links_url(), {
            "kind": ["photos", "videos", "photos"],
            "label": ["Day 1", "Reel", ""],
            "url": ["https://drive.google.com/drive/folders/AAA", "https://drive.google.com/drive/folders/BBB", ""],
        })
        self.assertEqual(r.status_code, 302)
        self.assertEqual(list(self.goa.memory_links.values_list("label", flat=True)), ["Day 1", "Reel"])  # blank row dropped
        html = self.client.get(reverse("trip_photos_videos", args=[self.goa.id])).content.decode()
        self.assertIn("https://drive.google.com/drive/folders/AAA", html)
        self.assertIn("drive.google.com", html)
        # saving again replaces the set (this is how links are updated)
        self.client.post(self._links_url(), {"kind": ["other"], "label": ["Docs"], "url": ["https://example.com/x"]})
        self.assertEqual(self.goa.memory_links.count(), 1)

    def test_drive_links_permissions_and_validation(self):
        data = {"kind": ["photos"], "label": ["x"], "url": ["https://drive.google.com/drive/folders/AAA"]}
        for who in ("viewer", "stranger"):
            self.client.login(username=who, password="pw")
            self.assertEqual(self.client.post(self._links_url(), data).status_code, 403, who)
        self.client.login(username="owner", password="pw")
        self.client.post(self._links_url(), data)
        # a bad row means NOTHING is changed, and javascript: links are refused
        self.client.post(self._links_url(), {"kind": ["photos"], "label": ["evil"], "url": ["javascript:alert(1)"]})
        self.assertEqual(list(self.goa.memory_links.values_list("label", flat=True)), ["x"])

    def test_memories_page_for_viewer_has_no_edit_controls(self):
        self.client.login(username="viewer", password="pw")
        html = self.client.get(reverse("trip_photos_videos", args=[self.goa.id])).content.decode()
        self.assertNotIn('id="manage-btn"', html)
        self.assertNotIn('id="cover-btn"', html)
        self.assertIn("No albums have been added yet", html)
        self.client.login(username="stranger", password="pw")
        self.assertEqual(self.client.get(reverse("trip_photos_videos", args=[self.goa.id])).status_code, 403)

    def test_memories_page_shows_expense_photos_and_highlights(self):
        self._exp(self.goa, 4200, receipt=_img("m.gif"), receipt_type="photo", location_name="Baga Beach")
        self.client.login(username="owner", password="pw")
        r = self.client.get(reverse("trip_photos_videos", args=[self.goa.id]))
        html = r.content.decode()
        self.assertEqual(len(r.context["moments"]), 1)
        self.assertIn("Baga Beach", html)
        self.assertIn("₹4,200", html)

    def test_trip7_seed_migration_logic(self):
        from importlib import import_module
        from django.apps import apps as real_apps
        mig = import_module("trip.migrations.0015_seed_trip7_drive_links")
        t7 = Trip.objects.create(id=7, name="Seven", destination="X", start_date=date.today() - timedelta(days=9),
                                 end_date=date.today() - timedelta(days=5), created_by=self.owner)
        mig.seed(real_apps, None)
        self.assertEqual(t7.memory_links.count(), 4)
        mig.seed(real_apps, None)                                  # idempotent
        self.assertEqual(t7.memory_links.count(), 4)

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
