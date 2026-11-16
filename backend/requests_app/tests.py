from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase
from django.utils import timezone
from datetime import timedelta
from .models import Category, ServiceRequest, WorkOrder


class ServiceRequestModelTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.requester = user_model.objects.create_user(username="requester")
        self.technician = user_model.objects.create_user(username="technician")
        self.category = Category.objects.create(name="Electrical")

    def make_request(self, **overrides):
        values = {
            "requester": self.requester,
            "category": self.category,
            "title": "Faulty socket",
            "description": "Socket does not supply power.",
            "location": "Software Engineering Lab",
            "priority": 2,
        }
        values.update(overrides)
        return ServiceRequest.objects.create(**values)

    def test_default_status_is_open(self):
        item = self.make_request()
        self.assertEqual(item.status, ServiceRequest.Status.OPEN)

    def test_priority_validator_rejects_zero(self):
        item = ServiceRequest(
            requester=self.requester,
            category=self.category,
            title="Invalid",
            description="Invalid priority.",
            location="Lab",
            priority=0,
        )
        with self.assertRaises(ValidationError):
            item.full_clean()

    def test_database_constraint_rejects_priority_six(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.make_request(priority=6)

    def test_category_in_use_is_protected(self):
        self.make_request()
        with self.assertRaises(ProtectedError):
            self.category.delete()

    def test_request_accepts_only_one_work_order(self):
        item = self.make_request()
        WorkOrder.objects.create(
            service_request=item,
            technician=self.technician,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                WorkOrder.objects.create(
                    service_request=item,
                    technician=self.technician,
                )
    def build(self, **overrides):
        values = {
            "requester": self.requester,
            "category": self.category,
            "title": "Rule test",
            "description": "Testing the resolution rule.",
            "location": "Lab",
            "priority": 2,
        }
        values.update(overrides)
        return ServiceRequest(**values)

    def test_resolved_requires_resolved_at_and_summary(self):
        item = self.build(status=ServiceRequest.Status.RESOLVED)
        with self.assertRaises(ValidationError) as ctx:
            item.full_clean()
        self.assertIn("resolved_at", ctx.exception.message_dict)
        self.assertIn("resolution_summary", ctx.exception.message_dict)

    def test_closed_requires_summary(self):
        item = self.build(status=ServiceRequest.Status.CLOSED, resolved_at=timezone.now())
        with self.assertRaises(ValidationError) as ctx:
            item.full_clean()
        self.assertIn("resolution_summary", ctx.exception.message_dict)

    def test_blank_summary_is_rejected(self):
        item = self.build(status=ServiceRequest.Status.RESOLVED, resolved_at=timezone.now(), resolution_summary="   ")
        with self.assertRaises(ValidationError):
            item.full_clean()

    def test_resolved_with_summary_and_timestamp_is_valid(self):
        item = self.build(status=ServiceRequest.Status.RESOLVED, resolved_at=timezone.now(), resolution_summary="Socket replaced.")
        item.full_clean()

    def test_open_request_needs_no_summary(self):
        self.build().full_clean()

    def test_due_before_filter(self):
        now = timezone.now()
        soon = self.make_request(title="Due soon", due_at=now + timedelta(days=1))
        self.make_request(title="Due later", due_at=now + timedelta(days=5))
        result = ServiceRequest.objects.filter(due_at__lt=now + timedelta(days=3))
        self.assertEqual(list(result), [soon])