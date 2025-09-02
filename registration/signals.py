# registration/signals.py
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.contrib.auth.models import User
from django.utils import timezone
from .models import Student, Payment, Receipt, AdminLog
from .utils import log_admin_action, get_client_ip

@receiver(post_save, sender=Student)
def log_student_action(sender, instance, created, **kwargs):
    """Log student creation/updates automatically"""
    # Only log if we have an active request with admin user
    # This avoids logging system-generated actions
    from django.contrib.admin import site
    from django.http import HttpRequest
    
    # Get the current request if available
    request = getattr(site, '_current_request', None)
    if request and hasattr(request, 'user') and request.user.is_staff:
        action = 'CREATE' if created else 'UPDATE'
        description = f'Student {instance.name} was {"created" if created else "updated"}'
        
        log_admin_action(
            user=request.user,
            action=action,
            model_name='Student',
            object_id=str(instance.id),
            description=description,
            ip_address=get_client_ip(request)
        )

@receiver(post_delete, sender=Student)
def log_student_deletion(sender, instance, **kwargs):
    """Log student deletions"""
    from django.contrib.admin import site
    
    request = getattr(site, '_current_request', None)
    if request and hasattr(request, 'user') and request.user.is_staff:
        log_admin_action(
            user=request.user,
            action='DELETE',
            model_name='Student',
            object_id=str(instance.id),
            description=f'Student {instance.name} was deleted',
            ip_address=get_client_ip(request)
        )

@receiver(post_save, sender=Payment)
def log_payment_action(sender, instance, created, **kwargs):
    """Log payment status changes"""
    from django.contrib.admin import site
    
    request = getattr(site, '_current_request', None)
    if request and hasattr(request, 'user') and request.user.is_staff:
        if created:
            description = f'Payment {instance.transaction_id} created for {instance.student.name}'
            action = 'CREATE'
        else:
            # Check if status was changed to SUCCESS (payment verification)
            if instance.status == 'SUCCESS':
                description = f'Payment {instance.transaction_id} verified for {instance.student.name}'
                action = 'PAYMENT_VERIFY'
            else:
                description = f'Payment {instance.transaction_id} updated'
                action = 'UPDATE'
        
        log_admin_action(
            user=request.user,
            action=action,
            model_name='Payment',
            object_id=str(instance.id),
            description=description,
            ip_address=get_client_ip(request)
        )

@receiver(post_save, sender=Receipt)
def log_receipt_generation(sender, instance, created, **kwargs):
    """Log receipt generation"""
    if created and instance.generated_by:
        log_admin_action(
            user=instance.generated_by,
            action='RECEIPT_GENERATE',
            model_name='Receipt',
            object_id=str(instance.id),
            description=f'Receipt {instance.receipt_number} generated for {instance.student.name}',
            ip_address=None  # IP not available in signal
        )

@receiver(user_logged_in)
def log_admin_login(sender, request, user, **kwargs):
    """Log admin user logins"""
    if user.is_staff:
        log_admin_action(
            user=user,
            action='LOGIN',
            description=f'Admin user logged in',
            ip_address=get_client_ip(request)
        )

@receiver(user_logged_out)
def log_admin_logout(sender, request, user, **kwargs):
    """Log admin user logouts"""
    if user and user.is_staff:
        log_admin_action(
            user=user,
            action='LOGOUT',
            description=f'Admin user logged out',
            ip_address=get_client_ip(request)
        )

# Custom middleware to track current request for signals
class AdminRequestMiddleware:
    """Middleware to make current request available to signals"""
    
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Store request in admin site for signals to access
        from django.contrib.admin import site
        site._current_request = request
        
        response = self.get_response(request)
        
        # Clean up
        if hasattr(site, '_current_request'):
            delattr(site, '_current_request')
        
        return response