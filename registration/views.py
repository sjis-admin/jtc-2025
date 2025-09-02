# registration/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_GET
from django.contrib import messages
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.utils import timezone
from django.db import transaction
from django.urls import reverse
from django_ratelimit.decorators import ratelimit
import requests
import json
import logging
import hashlib
import hmac
from decimal import Decimal
import qrcode
import io

from .models import Student, Event, Payment, Receipt, StudentEventRegistration, PaymentAttempt, School
from .forms import StudentRegistrationForm
from .utils import (
    get_client_ip, rate_limit_check, sanitize_payment_data, validate_student_data,
    verify_payment_amount, generate_secure_transaction_id, send_notification_email,
    log_security_alert, detect_suspicious_activity, verify_sslcommerz_callback,
    generate_sslcommerz_hash, log_admin_action
)

logger = logging.getLogger(__name__)
security_logger = logging.getLogger('registration.security')

@ratelimit(key='ip', rate='10/m', method='GET')
def home(request):
    """
    Home page with event listing and security monitoring
    """
    # Check for suspicious activity
    ip_address = get_client_ip(request)
    user_agent = request.META.get('HTTP_USER_AGENT', '')
    
    try:
        active_events = Event.objects.filter(is_active=True).order_by('created_at')
        active_events_list = list(active_events)
        
        # Get registration statistics for display
        stats = {
            'total_registrations': Student.objects.filter(is_deleted=False).count(),
            'active_events': len(active_events_list),
        }
        
        context = {
            'events': active_events_list,
            'stats': stats,
        }
        
        return render(request, 'registration/home.html', context)
        
    except Exception as e:
        logger.error(f'Error in home view: {e}')
        messages.error(request, 'An error occurred while loading the page.')
        return render(request, 'registration/home.html', {'events': [], 'stats': {}})

@ratelimit(key='ip', rate='10/m', method=['GET', 'POST'])
def register(request):
    """
    Student registration with comprehensive security measures
    """
    ip_address = get_client_ip(request)
    user_agent = request.META.get('HTTP_USER_AGENT', '')

    # Check rate limiting
    allowed, remaining = rate_limit_check(request, 'register', limit=20, period=3600)
    if not allowed:
        log_security_alert(
            'RATE_LIMIT',
            'Registration rate limit exceeded',
            ip_address,
            user_agent
        )
        messages.error(request, 'Too many registration attempts. Please try again later.')
        return redirect('home')

    if request.method == 'POST':
        form = StudentRegistrationForm(request.POST)

        if form.is_valid():
            try:
                with transaction.atomic():
                    school_college = form.cleaned_data.get('school_college')
                    other_school = form.cleaned_data.get('other_school')

                    if other_school:
                        school, created = School.objects.get_or_create(name=other_school)
                    else:
                        school = school_college

                    student = form.save(commit=False)
                    student.school_college = school
                    student.registration_ip = ip_address
                    student.save()

                    # Add selected events
                    events = form.cleaned_data['events']
                    total_amount = Decimal('0.00')

                    for event in events:
                        # Verify event is still available
                        can_register, message = student.can_register_for_event(event)
                        if not can_register:
                            raise ValueError(f"Cannot register for {event.name}: {message}")

                        StudentEventRegistration.objects.create(
                            student=student,
                            event=event,
                            registration_ip=ip_address
                        )
                        total_amount += event.fee

                    # Update total amount with security hash
                    student.total_amount = total_amount
                    student.save()

                    logger.info(f'Student registered successfully: {student.name} (ID: {student.registration_id})')

                    # Redirect to payment
                    messages.success(request, 'Registration successful! Please proceed with payment.')
                    return redirect('payment_gateway', student_id=student.id)

            except Exception as e:
                logger.error(f'Error during registration: {e}')
                log_security_alert(
                    'REGISTRATION_ERROR',
                    f'Registration failed: {str(e)}',
                    ip_address,
                    user_agent,
                    data={'error': str(e)}
                )
                messages.error(request, 'Registration failed. Please try again.')

    else:
        form = StudentRegistrationForm()

    return render(request, 'registration/register.html', {'form': form})

@require_GET
@ratelimit(key='ip', rate='30/m', method='GET')
def get_group(request):
    """
    HTMX endpoint to get group based on grade
    """
    grade = request.GET.get('grade')
    
    if grade:
        try:
            group = Student.calculate_group_from_grade(grade)
            group_display = dict(Student.GROUP_CHOICES).get(group, '')
            return HttpResponse(f'<span class="font-semibold text-blue-600">{group_display}</span>')
        except Exception:
            return HttpResponse('<span class="text-red-500">Invalid grade</span>')
    
    return HttpResponse('')

@require_POST
@ratelimit(key='ip', rate='30/m', method='POST')
def calculate_total(request):
    """
    HTMX endpoint to calculate total amount with security validation
    """
    try:
        event_ids = request.POST.getlist('events')
        
        if not event_ids:
            return HttpResponse('<span class="text-2xl font-bold text-gray-500">৳0.00</span>')
        
        # Validate event IDs
        try:
            event_ids = [int(id) for id in event_ids]
        except ValueError:
            return HttpResponse('<span class="text-red-500">Invalid event selection</span>')
        
        # Get active events only
        events = Event.objects.filter(id__in=event_ids, is_active=True)
        
        # Security check: ensure all requested events exist and are active
        if len(events) != len(event_ids):
            log_security_alert(
                'INVALID_EVENT',
                'Attempt to calculate total with invalid/inactive events',
                get_client_ip(request),
                request.META.get('HTTP_USER_AGENT', ''),
                data={'requested_events': event_ids, 'valid_events': list(events.values_list('id', flat=True))}
            )
            return HttpResponse('<span class="text-red-500">Invalid event selection</span>')
        
        total = sum(event.fee for event in events)
        
        return HttpResponse(f'<span class="text-2xl font-bold text-green-600">৳{total:,.2f}</span>')
        
    except Exception as e:
        logger.error(f'Error calculating total: {e}')
        return HttpResponse('<span class="text-red-500">Error calculating total</span>')

@ratelimit(key='ip', rate='10/m', method=['GET', 'POST'])
def payment_gateway(request, student_id):
    """
    SSL Commerz payment gateway integration with enhanced security
    """
    ip_address = get_client_ip(request)
    user_agent = request.META.get('HTTP_USER_AGENT', '')
    
    try:
        student = get_object_or_404(Student.objects.prefetch_related('events'), id=student_id, is_deleted=False)
        
        # Security check: prevent payment for already paid students
        if student.is_paid:
            messages.info(request, 'Payment has already been completed for this registration.')
            return redirect('home')
        
        # Check for too many payment attempts
        recent_attempts = PaymentAttempt.objects.filter(
            student=student,
            ip_address=ip_address,
            attempt_time__gte=timezone.now() - timezone.timedelta(hours=1)
        ).count()
        
        if recent_attempts >= settings.MAX_PAYMENT_ATTEMPTS_PER_HOUR:
            log_security_alert(
                'PAYMENT_ABUSE',
                f'Too many payment attempts for student {student.id}',
                ip_address,
                user_agent,
                student=student,
                data={'attempts_count': recent_attempts}
            )
            messages.error(request, 'Too many payment attempts. Please try again later.')
            return redirect('home')
        
        # Generate secure transaction ID
        transaction_id = generate_secure_transaction_id()
        
        # Create payment record with security measures
        payment = Payment.objects.create(
            student=student,
            transaction_id=transaction_id,
            amount=student.total_amount,
            client_ip=ip_address,
            payment_hash=hashlib.sha256(f"{transaction_id}{student.registration_id}{student.total_amount}".encode()).hexdigest()
        )
        
        # Log payment attempt
        PaymentAttempt.objects.create(
            student=student,
            ip_address=ip_address,
            user_agent=user_agent,
            success=False
        )
        
        # Prepare SSL Commerz data with sanitization
        post_data = sanitize_payment_data({
            'store_id': settings.SSLCOMMERZ_STORE_ID,
            'store_passwd': settings.SSLCOMMERZ_STORE_PASSWORD,
            'total_amount': float(student.total_amount),
            'currency': 'BDT',
            'tran_id': transaction_id,
            'success_url': settings.SITE_URL + reverse('payment_success', kwargs={'student_id': student.id}),
            'fail_url': settings.SITE_URL + reverse('payment_fail', kwargs={'student_id': student.id}),
            'cancel_url': settings.SITE_URL + reverse('payment_cancel', kwargs={'student_id': student.id}),
            'ipn_url': settings.SITE_URL + reverse('payment_ipn'),
            
            # Customer information (sanitized)
            'cus_name': student.name[:50],  # Limit length
            'cus_email': student.email,
            'cus_add1': student.school_college[:100],  # Limit length
            'cus_city': 'Dhaka',
            'cus_state': 'Dhaka',
            'cus_postcode': '1000',
            'cus_country': 'Bangladesh',
            'cus_phone': student.mobile_number,
            
            # Product information
            'product_name': f'JTC 2025 Registration - {student.name}',
            'product_category': 'Event Registration',
            'product_profile': 'general',
            
            # Shipping information
            'shipping_method': 'NO',
            'num_of_item': len(student.events.all()),
            
            # Security and validation
            'value_a': student.registration_id,  # For verification
            'value_b': payment.payment_hash,     # For integrity check
        })
        
        # SSL Commerz API endpoint
        if settings.SSLCOMMERZ_IS_SANDBOX:
            sslcommerz_url = 'https://sandbox.sslcommerz.com/gwprocess/v4/api.php'
        else:
            sslcommerz_url = 'https://securepay.sslcommerz.com/gwprocess/v4/api.php'
        
        try:
            response = requests.post(
                sslcommerz_url, 
                data=post_data,
                timeout=30,
                headers={'User-Agent': 'JTC-Registration-System/1.0'}
            )
            response.raise_for_status()
            
            response_data = response.json()
            
            if response_data.get('status') == 'SUCCESS':
                payment.sessionkey = response_data.get('sessionkey', '')
                payment.save()
                
                gateway_url = response_data.get('GatewayPageURL')
                if gateway_url:
                    logger.info(f'Payment gateway initiated for student {student.id}, transaction {transaction_id}')
                    return redirect(gateway_url)
                else:
                    raise ValueError('Gateway URL not provided')
            else:
                error_msg = response_data.get('failedreason', 'Payment gateway initialization failed')
                raise ValueError(error_msg)
                
        except requests.exceptions.RequestException as e:
            logger.error(f'SSL Commerz API error: {e}')
            raise ValueError('Payment gateway service unavailable')
        
    except Exception as e:
        # Log payment attempt as failed
        PaymentAttempt.objects.filter(
            student=student,
            ip_address=ip_address,
            success=False
        ).update(error_message=str(e))
        
        logger.error(f'Payment gateway error for student {student_id}: {e}')
        log_security_alert(
            'PAYMENT_ERROR',
            f'Payment gateway error: {str(e)}',
            ip_address,
            user_agent,
            student=student,
            data={'error': str(e), 'transaction_id': transaction_id if 'transaction_id' in locals() else None}
        )
        
        messages.error(request, 'Payment processing failed. Please try again.')
        return redirect('register')

@ratelimit(key='ip', rate='10/m', method='GET')
def payment_success(request, student_id):
    """
    Handle successful payment with comprehensive verification
    """
    ip_address = get_client_ip(request)
    user_agent = request.META.get('HTTP_USER_AGENT', '')
    
    try:
        student = get_object_or_404(Student.objects.prefetch_related('events'), id=student_id, is_deleted=False)
        
        # Get transaction details from SSL Commerz
        tran_id = request.GET.get('tran_id')
        val_id = request.GET.get('val_id')
        amount = request.GET.get('amount')
        card_type = request.GET.get('card_type', '')
        
        if not all([tran_id, val_id, amount]):
            raise ValueError('Missing required payment parameters')
        
        # Get payment record
        try:
            payment = Payment.objects.get(transaction_id=tran_id, student=student)
        except Payment.DoesNotExist:
            log_security_alert(
                'PAYMENT_FRAUD',
                f'Payment success callback for non-existent transaction: {tran_id}',
                ip_address,
                user_agent,
                student=student,
                data={'tran_id': tran_id, 'val_id': val_id}
            )
            messages.error(request, 'Invalid payment transaction.')
            return redirect('home')
        
        # Verify integrity of the callback
        registration_id = request.GET.get('value_a')
        received_hash = request.GET.get('value_b')

        if registration_id != str(payment.student.registration_id):
            log_security_alert(
                'PAYMENT_FRAUD',
                'Registration ID mismatch in payment success callback',
                ip_address,
                user_agent,
                student=student,
                payment=payment,
                data={'expected': str(payment.student.registration_id), 'received': registration_id}
            )
            messages.error(request, 'Invalid payment transaction.')
            return redirect('home')

        if not hmac.compare_digest(payment.payment_hash, received_hash):
            log_security_alert(
                'PAYMENT_FRAUD',
                'Payment hash mismatch in payment success callback',
                ip_address,
                user_agent,
                student=student,
                payment=payment,
                data={'expected': payment.payment_hash, 'received': received_hash}
            )
            messages.error(request, 'Invalid payment transaction.')
            return redirect('home')

        # Prevent duplicate processing
        if payment.status == 'SUCCESS':
            messages.info(request, 'Payment has already been processed.')
            return render(request, 'registration/payment_success.html', {
                'student': student, 
                'payment': payment
            })
        
        # Verify payment amount - CRITICAL SECURITY CHECK
        if not verify_payment_amount(payment.amount, amount):
            log_security_alert(
                'PAYMENT_FRAUD',
                f'Payment amount mismatch - Expected: {payment.amount}, Received: {amount}',
                ip_address,
                user_agent,
                student=student,
                payment=payment,
                data={'expected_amount': str(payment.amount), 'received_amount': amount}
            )
            messages.error(request, 'Payment amount verification failed.')
            return redirect('payment_fail', student_id=student.id)
        
        # Validate with SSL Commerz
        validation_data = {
            'val_id': val_id,
            'store_id': settings.SSLCOMMERZ_STORE_ID,
            'store_passwd': settings.SSLCOMMERZ_STORE_PASSWORD,
            'format': 'json'
        }
        
        validation_url = ('https://sandbox.sslcommerz.com/validator/api/validationserverAPI.php' 
                         if settings.SSLCOMMERZ_IS_SANDBOX 
                         else 'https://securepay.sslcommerz.com/validator/api/validationserverAPI.php')
        
        try:
            validation_response = requests.get(
                validation_url, 
                params=validation_data,
                timeout=30,
                headers={'User-Agent': 'JTC-Registration-System/1.0'}
            )
            validation_response.raise_for_status()
            validation_result = validation_response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f'SSL Commerz validation error: {e}')
            messages.error(request, 'Payment verification failed. Please contact support.')
            return redirect('payment_fail', student_id=student.id)
        
        # Verify hash signature if present
        callback_data = dict(request.GET.items())
        if not verify_sslcommerz_callback(callback_data, settings.SSLCOMMERZ_STORE_PASSWORD):
            log_security_alert(
                'INVALID_HASH',
                'SSL Commerz callback hash verification failed',
                ip_address,
                user_agent,
                student=student,
                payment=payment,
                data={'callback_data': callback_data}
            )
            messages.error(request, 'Payment verification failed.')
            return redirect('payment_fail', student_id=student.id)
        
        # Final verification checks
        if (validation_result.get('status') == 'VALID' and 
            validation_result.get('tran_id') == tran_id and
            verify_payment_amount(payment.amount, validation_result.get('amount', 0))):
            
            try:
                with transaction.atomic():
                    # Update payment status
                    payment.status = 'SUCCESS'
                    payment.payment_method = card_type.upper() if card_type else 'UNKNOWN'
                    payment.gateway_txnid = val_id
                    payment.gateway_response = validation_result
                    payment.completed_at = timezone.now()
                    payment.save()
                    
                    # Update student status
                    student.is_paid = True
                    student.payment_verified = True
                    student.save()
                    
                    # Mark payment attempt as successful
                    PaymentAttempt.objects.filter(
                        student=student,
                        ip_address=ip_address,
                        success=False
                    ).update(success=True)
                    
                    # Generate receipt
                    receipt, created = Receipt.objects.get_or_create(
                        student=student,
                        payment=payment,
                        defaults={'generated_by': None}
                    )
                    
                    logger.info(f'Payment successful for student {student.id}, transaction {tran_id}')
                    
                    # Send confirmation email asynchronously
                    try:
                        send_registration_email(student, receipt)
                    except Exception as email_error:
                        logger.error(f'Failed to send confirmation email: {email_error}')
                        # Don't fail the payment for email issues
                    
                    messages.success(request, 'Payment successful! Confirmation email has been sent.')
                    
                    context = {
                        'student': student,
                        'payment': payment,
                        'receipt': receipt,
                        'events': student.events.all()
                    }
                    return render(request, 'registration/payment_success.html', context)
                    
            except Exception as e:
                logger.error(f'Error updating payment status: {e}')
                messages.error(request, 'Payment processing error. Please contact support.')
                return redirect('payment_fail', student_id=student.id)
        else:
            # Payment validation failed
            payment.status = 'FAILED'
            payment.gateway_response = validation_result
            payment.save()
            
            log_security_alert(
                'PAYMENT_FRAUD',
                f'Payment validation failed - Status: {validation_result.get("status")}, Amount mismatch or ID mismatch',
                ip_address,
                user_agent,
                student=student,
                payment=payment,
                data=validation_result
            )
            
            messages.error(request, 'Payment verification failed.')
            return redirect('payment_fail', student_id=student.id)
            
    except Exception as e:
        logger.error(f'Payment success handler error: {e}')
        log_security_alert(
            'PAYMENT_ERROR',
            f'Payment success handler error: {str(e)}',
            ip_address,
            user_agent,
            data={'error': str(e), 'student_id': student_id}
        )
        messages.error(request, 'Payment processing error.')
        return redirect('payment_fail', student_id=student_id)

@ratelimit(key='ip', rate='10/m', method='GET')
def payment_fail(request, student_id):
    """
    Handle failed payment
    """
    try:
        student = get_object_or_404(Student, id=student_id, is_deleted=False)
        
        # Get transaction details
        tran_id = request.GET.get('tran_id')
        error_msg = request.GET.get('error', 'Payment failed')
        
        # Update payment status if exists
        if tran_id:
            try:
                payment = Payment.objects.get(transaction_id=tran_id, student=student)
                payment.status = 'FAILED'
                payment.gateway_response = dict(request.GET.items())
                payment.save()
                
                logger.info(f'Payment failed for student {student.id}, transaction {tran_id}')
            except Payment.DoesNotExist:
                pass
        
        context = {
            'student': student,
            'error_message': error_msg
        }
        return render(request, 'registration/payment_fail.html', context)
        
    except Exception as e:
        logger.error(f'Payment fail handler error: {e}')
        messages.error(request, 'An error occurred.')
        return redirect('home')

@ratelimit(key='ip', rate='10/m', method='GET')
def payment_cancel(request, student_id):
    """
    Handle cancelled payment
    """
    try:
        student = get_object_or_404(Student, id=student_id, is_deleted=False)
        
        # Get transaction details
        tran_id = request.GET.get('tran_id')
        
        # Update payment status if exists
        if tran_id:
            try:
                payment = Payment.objects.get(transaction_id=tran_id, student=student)
                payment.status = 'CANCELLED'
                payment.gateway_response = dict(request.GET.items())
                payment.save()
                
                logger.info(f'Payment cancelled for student {student.id}, transaction {tran_id}')
            except Payment.DoesNotExist:
                pass
        
        context = {
            'student': student
        }
        return render(request, 'registration/payment_cancel.html', context)
        
    except Exception as e:
        logger.error(f'Payment cancel handler error: {e}')
        messages.error(request, 'An error occurred.')
        return redirect('home')

@csrf_exempt
@require_POST
@ratelimit(key='ip', rate='30/m', method='POST')
def payment_ipn(request):
    """
    Handle SSL Commerz IPN (Instant Payment Notification) with enhanced security and idempotency.
    This view is responsible for receiving asynchronous notifications from SSL Commerz
    about the status of a transaction.
    """
    ip_address = get_client_ip(request)
    user_agent = request.META.get('HTTP_USER_AGENT', '')
    
    logger.info(f"IPN received from {ip_address}")

    try:
        ipn_data = request.POST.dict()
        tran_id = ipn_data.get('tran_id')
        status = ipn_data.get('status')

        logger.info(f"IPN data for tran_id {tran_id}: {ipn_data}")

        # 1. Verify the authenticity of the IPN callback
        if not verify_sslcommerz_callback(ipn_data, settings.SSLCOMMERZ_STORE_PASSWORD):
            log_security_alert('INVALID_HASH', 'IPN hash verification failed', ip_address, user_agent, data=ipn_data)
            logger.warning(f"IPN hash verification failed for tran_id: {tran_id}")
            return HttpResponseBadRequest('Invalid signature')

        # 2. Check for required parameters
        val_id = ipn_data.get('val_id')
        amount = ipn_data.get('amount')
        if not all([tran_id, status, val_id, amount]):
            logger.error(f"IPN missing required parameters for tran_id: {tran_id}")
            return HttpResponseBadRequest('Missing required parameters')

        # 3. Retrieve the payment record
        try:
            payment = Payment.objects.get(transaction_id=tran_id)
        except Payment.DoesNotExist:
            log_security_alert('PAYMENT_FRAUD', f'IPN for non-existent transaction: {tran_id}', ip_address, user_agent, data=ipn_data)
            logger.warning(f"IPN received for non-existent tran_id: {tran_id}")
            return HttpResponseBadRequest('Transaction not found')

        # 4. Idempotency Check: If payment is already successful, do nothing.
        if payment.status == 'SUCCESS':
            logger.info(f"IPN for already successful payment {tran_id} received. Skipping.")
            return HttpResponse('OK', status=200)

        # 5. Verify the payment amount
        if not verify_payment_amount(payment.amount, amount):
            log_security_alert('PAYMENT_FRAUD', f'IPN amount mismatch - Expected: {payment.amount}, Received: {amount}', ip_address, user_agent, payment=payment, data=ipn_data)
            logger.warning(f"IPN amount mismatch for tran_id: {tran_id}")
            return HttpResponseBadRequest('Amount mismatch')

        # 6. Process the IPN based on the status
        with transaction.atomic():
            if status.upper() == 'VALID':
                # Mark payment as successful
                payment.status = 'SUCCESS'
                payment.gateway_txnid = val_id
                payment.gateway_response = ipn_data
                payment.completed_at = timezone.now()
                payment.save()

                # Update student record
                student = payment.student
                student.is_paid = True
                student.payment_verified = True
                student.save()

                logger.info(f'Payment for tran_id {tran_id} successfully updated to SUCCESS via IPN.')

                # Optionally, send confirmation email here if not already sent
                # This is a good fallback if the user closes the browser before the success page loads
                receipt, created = Receipt.objects.get_or_create(student=student, payment=payment)
                if not receipt.email_sent:
                    send_registration_email(student, receipt)

            elif status.upper() in ['FAILED', 'CANCELLED', 'EXPIRED']:
                # Mark payment with the terminal status
                payment.status = status.upper()
                payment.gateway_response = ipn_data
                payment.save()
                logger.info(f'Payment for tran_id {tran_id} updated to {payment.status} via IPN.')

            else:
                logger.warning(f"IPN for tran_id {tran_id} received with unhandled status: {status}")

        return HttpResponse('OK', status=200)

    except Exception as e:
        logger.error(f'IPN processing error: {e}')
        log_security_alert('IPN_ERROR', f'IPN processing error: {str(e)}', ip_address, user_agent, data={'error': str(e)})
        return HttpResponseBadRequest('Processing error')

from .utils import (
    get_client_ip, rate_limit_check, sanitize_payment_data, validate_student_data,
    verify_payment_amount, generate_secure_transaction_id, send_notification_email,
    log_security_alert, detect_suspicious_activity, verify_sslcommerz_callback,
    generate_sslcommerz_hash, log_admin_action, send_email_async
)

def send_registration_email(student, receipt):
    """
    Send registration confirmation email with receipt asynchronously.
    """
    try:
        subject = f'JTC 2025 Registration Confirmation - {student.name}'
        
        # Prepare context for email template
        context = {
            'student': student,
            'receipt': receipt,
            'events': student.events.all(),
            'payment': receipt.payment if receipt else None,
        }
        
        # Render email template
        html_message = render_to_string('registration/email/registration_confirmation.html', context)
        plain_message = strip_tags(html_message)
        
        # Send email asynchronously
        send_email_async(
            subject=subject,
            message=plain_message,
            from_email=settings.EMAIL_HOST_USER,
            recipient_list=[student.email],
            html_message=html_message
        )
        
        # Update receipt
        if receipt:
            receipt.email_sent = True
            receipt.email_sent_at = timezone.now()
            receipt.save()
        
        logger.info(f'Registration email queued for {student.email}')
        return True
        
    except Exception as e:
        logger.error(f'Failed to queue registration email for {student.email}: {e}')
        return False

def generate_qr_code(request, receipt_number):
    """
    Generate a QR code for the given receipt number.
    """
    try:
        receipt = get_object_or_404(Receipt, receipt_number=receipt_number)
        verification_url = request.build_absolute_uri(
            reverse('verify_receipt', kwargs={'receipt_number': receipt.receipt_number})
        )
        
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(verification_url)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")
        
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        return HttpResponse(buffer.getvalue(), content_type="image/png")

    except Exception as e:
        logger.error(f"Error generating QR code for receipt {receipt_number}: {e}")
        return HttpResponse(status=500)

def verify_receipt(request, receipt_number):
    """
    Verify a receipt and display its status.
    """
    try:
        receipt = get_object_or_404(Receipt.objects.select_related('student', 'payment'), receipt_number=receipt_number)
        context = {
            'receipt': receipt,
            'student': receipt.student,
            'payment': receipt.payment,
        }
        return render(request, 'registration/verify_receipt.html', context)
    except Exception as e:
        logger.error(f"Error verifying receipt {receipt_number}: {e}")
        messages.error(request, "An error occurred while verifying the receipt.")
        return redirect('home')
