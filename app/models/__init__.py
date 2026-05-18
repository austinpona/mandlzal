"""Aggregate model imports so `Base.metadata` is fully populated."""
from app.models.user import User  # noqa: F401
from app.models.customer import Customer, CustomerStatus  # noqa: F401
from app.models.policy import Policy, PolicyType, PolicyStatus, BillingCycle  # noqa: F401
from app.models.member import Member, MemberStatus  # noqa: F401
from app.models.payment import Payment, PaymentMethod, PaymentStatus  # noqa: F401
from app.models.audit import AuditLog  # noqa: F401
from app.models.notification import Notification  # noqa: F401
from app.models.cover_plan import CoverPlan, CoverCategory  # noqa: F401
from app.models.beneficiary import Beneficiary  # noqa: F401
from app.models.device import Device, DeviceEnrollmentCode, DeviceStatus  # noqa: F401
from app.models.field_submission import FieldSubmission, FieldSubmissionStatus  # noqa: F401
