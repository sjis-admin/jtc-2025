# registration/models.py
from django.db import models
from django.contrib.auth.models import User
from django.core.validators import RegexValidator
from django.utils import timezone
from django.core.validators import RegexValidator, MinValueValidator, MaxValueValidator
from cryptography.fernet import Fernet
from django.conf import settings
import uuid
import base64
from django.core.exceptions import ValidationError
from decimal import Decimal
import hashlib

class School(models.Model):
    name = models.CharField(max_length=300, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

from django.core.exceptions import ImproperlyConfigured

class EncryptedField(models.TextField):
    """Custom field for encrypting sensitive data"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Generate or get encryption key
        key = getattr(settings, 'ENCRYPTION_KEY', None)
        if key is None:
            raise ImproperlyConfigured(
                "You must set the ENCRYPTION_KEY in your settings file. "
                "You can generate a new key with: from cryptography.fernet import Fernet; Fernet.generate_key()"
            )
        self.cipher_suite = Fernet(key)
    
    def from_db_value(self, value, expression, connection):
        if value is None:
            return value
        try:
            # Decrypt the value
            return self.cipher_suite.decrypt(value.encode()).decode()
        except Exception as e:
            # Log the error and return the raw value
            # In a real application, you might want to handle this differently
            print(f"Error decrypting value: {e}")
            return value
    
    def to_python(self, value):
        if isinstance(value, str) or value is None:
            return value
        return str(value)
    
    def get_prep_value(self, value):
        if value is None:
            return value
        # Encrypt the value
        return self.cipher_suite.encrypt(value.encode()).decode()

class Event(models.Model):
    EVENT_TYPE_CHOICES = [
        ('INDIVIDUAL', 'Individual'),
        ('TEAM', 'Team'),
    ]

    name = models.CharField(max_length=200)
    description = models.TextField()
    fee = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=500.00,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    is_active = models.BooleanField(default=True)
    max_participants = models.PositiveIntegerField(null=True, blank=True, help_text="Keep blank for unlimited participants.")
    
    # New fields for event type
    event_type = models.CharField(
        max_length=10,
        choices=EVENT_TYPE_CHOICES,
        default='INDIVIDUAL',
        help_text="Select 'Team' for team-based events."
    )
    max_team_size = models.PositiveIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(2)],
        help_text="Required if event type is 'Team'. Minimum 2 members."
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def clean(self):
        if self.event_type == 'TEAM' and not self.max_team_size:
            raise ValidationError({'max_team_size': "Max team size is required for team events."})
        if self.event_type == 'INDIVIDUAL' and self.max_team_size:
            self.max_team_size = None

    def __str__(self):
        return self.name
    
    def get_registration_count(self):
        return self.student_set.count()
    
    def is_registration_full(self):
        if self.max_participants:
            return self.get_registration_count() >= self.max_participants
        return False

class Student(models.Model):
    GRADE_CHOICES = [
        ('3', 'Grade 3'),
        ('4', 'Grade 4'),
        ('5', 'Grade 5'),
        ('6', 'Grade 6'),
        ('7', 'Grade 7'),
        ('8', 'Grade 8'),
        ('9', 'Grade 9'),
        ('10', 'Grade 10'),
        ('11', 'Grade 11'),
        ('12', 'Grade 12'),
    ]
    
    GROUP_CHOICES = [
        ('A', 'Group A (Grade 3-4)'),
        ('B', 'Group B (Grade 5-6)'),
        ('C', 'Group C (Grade 7-8)'),
        ('D', 'Group D (Grade 9-12)'),
    ]
    
    # Basic Information
    name = models.CharField(max_length=200)
    school_college = models.ForeignKey(School, on_delete=models.SET_NULL, null=True, blank=True)
    other_school = models.CharField(max_length=300, blank=True, null=True)
    grade = models.CharField(max_length=2, choices=GRADE_CHOICES)
    group = models.CharField(max_length=1, choices=GROUP_CHOICES, editable=False)
    section = models.CharField(max_length=50, blank=True, null=True, help_text="Only for SJIS students")
    roll = models.CharField(max_length=50, help_text="Unique identification from school")
    
    # Contact Information (Encrypted)
    email = models.EmailField()
    mobile_regex = RegexValidator(
        regex=r'^\+?1?\d{9,15}$', 
        message="Phone number must be entered in the format: '+999999999'. Up to 15 digits allowed."
    )
    mobile_number = models.CharField(validators=[mobile_regex], max_length=17)
    
    # Registration Details
    events = models.ManyToManyField(Event, through='StudentEventRegistration')
    registration_id = models.CharField(max_length=20, unique=True, editable=False)
    total_amount = models.DecimalField(
    max_digits=10,
    decimal_places=2,
    default=0.00,
    validators=[MinValueValidator(Decimal('0.00'))]   # ✅ fixed
    )
    is_paid = models.BooleanField(default=False)
    payment_verified = models.BooleanField(default=False)
    payment_verification_hash = models.CharField(max_length=64, blank=True)
    
    # Security and Audit
    registration_ip = models.GenericIPAddressField(null=True, blank=True)
    is_deleted = models.BooleanField(default=False)  # Soft delete
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['registration_id']),
            models.Index(fields=['is_paid']),
            models.Index(fields=['created_at']),
        ]
    
    def clean(self):
        super().clean()
        # Validate grade and group consistency
        if self.grade:
            expected_group = self.calculate_group_from_grade(self.grade)
            if self.group and self.group != expected_group:
                raise ValidationError(f"Grade {self.grade} should be in Group {expected_group}")
    
    def save(self, *args, **kwargs):
        # Auto-assign group based on grade ranges
        if self.grade:
            self.group = self.calculate_group_from_grade(self.grade)

        if not self.registration_id:
            current_year = timezone.now().strftime('%y')
            prefix = f'JTC{current_year}'
            last_student = Student.objects.filter(registration_id__startswith=prefix).order_by('registration_id').last()
            
            if last_student:
                last_id = int(last_student.registration_id[len(prefix):])
                new_id = last_id + 1
            else:
                new_id = 1
            
            self.registration_id = f'{prefix}{new_id:04d}'
        
        # Generate payment verification hash
        if not self.payment_verification_hash:
            self.payment_verification_hash = self.generate_verification_hash()
        
        super().save(*args, **kwargs)
    
    @staticmethod
    def calculate_group_from_grade(grade):
        """Calculate group based on grade"""
        try:
            grade_int = int(grade)
            if 3 <= grade_int <= 4:
                return 'A'
            elif 5 <= grade_int <= 6:
                return 'B'
            elif 7 <= grade_int <= 8:
                return 'C'
            elif 9 <= grade_int <= 12:
                return 'D'
            else:
                raise ValidationError(f"Invalid grade: {grade}")
        except (ValueError, TypeError):
            raise ValidationError(f"Invalid grade format: {grade}")
    
    def generate_verification_hash(self):
        """Generate verification hash for payment security"""
        data = f"{self.registration_id}{self.email}{self.total_amount}"
        return hashlib.sha256(data.encode()).hexdigest()
    
    def calculate_total_amount(self):
        """Calculate and update total amount"""
        total = sum([event.fee for event in self.events.all()])
        self.total_amount = total
        # Regenerate hash when amount changes
        self.payment_verification_hash = self.generate_verification_hash()
        return total
    
    def verify_payment_integrity(self, received_amount):
        """Verify payment amount matches expected amount"""
        expected = float(self.total_amount)
        received = float(received_amount)
        return abs(expected - received) < 0.01
    
    def can_register_for_event(self, event):
        """Check if student can register for an event"""
        if not event.is_active:
            return False, "Event is not active"
        if event.is_registration_full():
            return False, "Event registration is full"
        if self.events.filter(id=event.id).exists():
            return False, "Already registered for this event"
        return True, "Can register"
    
    def __str__(self):
        return f"{self.name} - {self.school_college}"


class Team(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='teams')
    name = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class TeamMember(models.Model):
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='members')
    name = models.CharField(max_length=200, default="")
    is_leader = models.BooleanField(default=False)

    def __str__(self):
        return f'{self.name} - {self.team.name}'

class StudentEventRegistration(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    team = models.ForeignKey(Team, on_delete=models.SET_NULL, null=True, blank=True)
    registered_at = models.DateTimeField(auto_now_add=True)
    registration_ip = models.GenericIPAddressField(null=True, blank=True)
    
    class Meta:
        unique_together = ['student', 'event']
        indexes = [
            models.Index(fields=['registered_at']),
        ]

class Payment(models.Model):
    PAYMENT_STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('SUCCESS', 'Success'),
        ('FAILED', 'Failed'),
        ('CANCELLED', 'Cancelled'),
        ('EXPIRED', 'Expired'),
    ]
    
    PAYMENT_METHOD_CHOICES = [
        ('BKASH', 'bKash'),
        ('ROCKET', 'Rocket'),
        ('NAGAD', 'Nagad'),
        ('CARD', 'Credit/Debit Card'),
        ('UPAY', 'Upay'),
        ('OTHER', 'Other'),
    ]
    
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='payments')
    transaction_id = models.CharField(max_length=100, unique=True, db_index=True)
    amount = models.DecimalField(
    max_digits=10,
    decimal_places=2,
    validators=[MinValueValidator(Decimal('0.01'))]   # ✅ fixed
    )
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, blank=True)
    status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='PENDING')
    
    # SSL Commerz specific fields
    sessionkey = models.CharField(max_length=200, blank=True)
    gateway_txnid = models.CharField(max_length=200, blank=True)
    gateway_response = models.JSONField(blank=True, null=True)
    
    # Security fields
    payment_hash = models.CharField(max_length=64, blank=True)
    verification_signature = models.CharField(max_length=128, blank=True)
    client_ip = models.GenericIPAddressField(null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['transaction_id']),
            models.Index(fields=['status']),
            models.Index(fields=['created_at']),
        ]
    
    def save(self, *args, **kwargs):
        # Set expiration time if not set
        if not self.expires_at and self.status == 'PENDING':
            self.expires_at = timezone.now() + timezone.timedelta(
                minutes=getattr(settings, 'PAYMENT_TIMEOUT_MINUTES', 15)
            )
        
        # Set completion time when marked as success
        if self.status == 'SUCCESS' and not self.completed_at:
            self.completed_at = timezone.now()
        
        super().save(*args, **kwargs)
    
    def generate_payment_hash(self):
        """Generate secure hash for payment verification"""
        data = f"{self.transaction_id}{self.student.registration_id}{self.amount}"
        return hashlib.sha256(data.encode()).hexdigest()
    
    def verify_ssl_commerz_signature(self, received_data):
        """Verify SSL Commerz callback signature"""
        from .utils import generate_sslcommerz_hash
        expected_hash = generate_sslcommerz_hash(received_data, settings.SSLCOMMERZ_STORE_PASSWORD)
        received_hash = received_data.get('verify_sign', '')
        return expected_hash == received_hash
    
    def is_expired(self):
        """Check if payment has expired"""
        if self.expires_at and self.status == 'PENDING':
            return timezone.now() > self.expires_at
        return False
    
    def mark_expired(self):
        """Mark payment as expired"""
        if self.is_expired() and self.status == 'PENDING':
            self.status = 'EXPIRED'
            self.save()
    
    def __str__(self):
        return f"Payment {self.transaction_id} - {self.student.name}"

class PaymentAttempt(models.Model):
    """Track payment attempts for security monitoring"""
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField(blank=True)
    attempt_time = models.DateTimeField(auto_now_add=True)
    success = models.BooleanField(default=False)
    error_message = models.TextField(blank=True)
    
    class Meta:
        ordering = ['-attempt_time']
        indexes = [
            models.Index(fields=['ip_address', 'attempt_time']),
        ]

class AdminLog(models.Model):
    ACTION_CHOICES = [
        ('CREATE', 'Created'),
        ('UPDATE', 'Updated'),
        ('DELETE', 'Deleted'),
        ('LOGIN', 'Logged In'),
        ('LOGOUT', 'Logged Out'),
        ('PAYMENT_VERIFY', 'Payment Verified'),
        ('PAYMENT_REJECT', 'Payment Rejected'),
        ('RECEIPT_GENERATE', 'Receipt Generated'),
        ('EMAIL_SENT', 'Email Sent'),
        ('BULK_UPDATE', 'Bulk Update'),
        ('SECURITY_ALERT', 'Security Alert'),
    ]
    
    admin_user = models.ForeignKey(User, on_delete=models.CASCADE)
    action = models.CharField(max_length=20, choices=ACTION_CHOICES, db_index=True)
    model_name = models.CharField(max_length=50, blank=True)
    object_id = models.CharField(max_length=50, blank=True)
    description = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['admin_user', 'timestamp']),
            models.Index(fields=['action', 'timestamp']),
        ]
    
    def __str__(self):
        return f"{self.admin_user.username} - {self.action} - {self.timestamp}"

from django.db import transaction

class Receipt(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='receipts')
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name='receipts')
    receipt_number = models.CharField(max_length=20, unique=True, db_index=True)
    generated_at = models.DateTimeField(auto_now_add=True)
    generated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    email_sent = models.BooleanField(default=False)
    email_sent_at = models.DateTimeField(blank=True, null=True)
    download_count = models.PositiveIntegerField(default=0)
    last_downloaded_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-generated_at']
        indexes = [
            models.Index(fields=['receipt_number']),
            models.Index(fields=['generated_at']),
        ]
    
    def save(self, *args, **kwargs):
        if not self.receipt_number:
            with transaction.atomic():
                # Lock the table to prevent race conditions
                last_receipt = Receipt.objects.select_for_update().order_by('id').last()
                if last_receipt:
                    last_number = int(last_receipt.receipt_number.split('-')[1])
                    self.receipt_number = f"JTC2025-{last_number + 1:04d}"
                else:
                    self.receipt_number = "JTC2025-0001"
        super().save(*args, **kwargs)
    
    def record_download(self):
        """Record receipt download"""
        self.download_count += 1
        self.last_downloaded_at = timezone.now()
        self.save(update_fields=['download_count', 'last_downloaded_at'])
    
    def __str__(self):
        return f"Receipt {self.receipt_number} - {self.student.name}"

class SecurityAlert(models.Model):
    """Track security-related events"""
    ALERT_TYPES = [
        ('PAYMENT_FRAUD', 'Payment Fraud Attempt'),
        ('RATE_LIMIT', 'Rate Limit Exceeded'),
        ('INVALID_HASH', 'Invalid Hash Verification'),
        ('SUSPICIOUS_IP', 'Suspicious IP Activity'),
        ('MULTIPLE_REGISTRATIONS', 'Multiple Registrations'),
    ]
    
    alert_type = models.CharField(max_length=30, choices=ALERT_TYPES)
    description = models.TextField()
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField(blank=True)
    related_student = models.ForeignKey(Student, on_delete=models.SET_NULL, null=True, blank=True)
    related_payment = models.ForeignKey(Payment, on_delete=models.SET_NULL, null=True, blank=True)
    data = models.JSONField(blank=True, null=True)
    resolved = models.BooleanField(default=False)
    resolved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['alert_type', 'created_at']),
            models.Index(fields=['ip_address']),
        ]
    
    def __str__(self):
        return f"{self.get_alert_type_display()} - {self.created_at}"

class Countdown(models.Model):
    title = models.CharField(max_length=200)
    target_date = models.DateTimeField()
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.title