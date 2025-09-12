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

import logging

logger = logging.getLogger(__name__)

from .models import (Student, Event, Payment, Receipt, 
                    StudentEventRegistration, PaymentAttempt, School, 
                    Team, TeamMember, Countdown, HomePageAsset, SocialMediaProfile,
                    TeamMemberProfile, PastEventImage)
from .forms import StudentRegistrationForm
from .sslcommerz import SSLCOMMERZ

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

        # Get active countdown timer
        countdown = Countdown.objects.filter(is_active=True).first()

        # Get home page assets
        home_page_assets = HomePageAsset.objects.filter(is_active=True)
        slideshow_images = home_page_assets.filter(asset_type='IMAGE')
        background_video = home_page_assets.filter(asset_type='VIDEO').first()

        # Get social media profiles
        social_media_profiles = SocialMediaProfile.objects.filter(is_active=True)
        
        context = {
            'events': active_events_list,
            'stats': stats,
            'countdown': countdown,
            'slideshow_images': slideshow_images,
            'background_video': background_video,
            'social_media_profiles': social_media_profiles,
        }
        
        return render(request, 'registration/home.html', context)
        
    except Exception as e:
        logger.error(f'Error in home view: {e}')
        messages.error(request, 'An error occurred while loading the page.')
        return render(request, 'registration/home.html', {'events': [], 'stats': {}, 'countdown': None})

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
                    team_event_selected = any(event.event_type == 'TEAM' for event in events)

                    team = None
                    if team_event_selected:
                        team_name = request.POST.get('team_name')
                        if not team_name:
                            raise ValueError("Team name is required for team events.")
                        
                        team = Team.objects.create(name=team_name, event=events.filter(event_type='TEAM').first())
                        
                        team_members = []
                        for i in range(1, 100): # Assuming max 99 team members
                            member_name = request.POST.get(f'team_member_{i}')
                            if not member_name:
                                break
                            team_members.append(member_name)

                        logger.info(f'Team members from form: {team_members}')

                        leader_index = request.POST.get('team_leader')
                        
                        for i, member_name in enumerate(team_members):
                            TeamMember.objects.create(team=team, name=member_name, is_leader=(leader_index == str(i + 1)))


                    for event in events:
                        # Verify event is still available
                        can_register, message = student.can_register_for_event(event)
                        if not can_register:
                            raise ValueError(f"Cannot register for {event.name}: {message}")

                        StudentEventRegistration.objects.create(
                            student=student,
                            event=event,
                            team=team if event.event_type == 'TEAM' else None,
                            registration_ip=ip_address
                        )
                        total_amount += event.fee

                    # Update total amount with security hash
                    student.total_amount = total_amount
                    student.save()

                    logger.info(f'Student registered successfully: {student.name} (ID: {student.registration_id})')

                    # Redirect to payment
                    messages.success(request, 'Registration successful!')
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
        sslcommerz = SSLCOMMERZ()
        response_data = sslcommerz.create_session(
            amount=student.total_amount,
            tran_id=transaction_id,
            cust_name=student.name,
            cust_email=student.email,
            cust_phone=student.mobile_number,
            student_id=student.id,
            cus_add1=student.school_college.name,
            cus_city='Dhaka',
            cus_state='Dhaka',
            cus_postcode='1000',
            cus_country='Bangladesh'
        )

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
            logger.error(f"SSL Commerz payment gateway initialization failed. Response: {response_data}")
            error_msg = response_data.get('failedreason', 'Payment gateway initialization failed')
            raise ValueError(error_msg)
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

@csrf_exempt
@ratelimit(key='ip', rate='10/m', method=['GET', 'POST'])
def payment_success(request, student_id):
    """
    Handle successful payment with comprehensive verification
    """
    ip_address = get_client_ip(request)
    user_agent = request.META.get('HTTP_USER_AGENT', '')
    
    try:
        student = get_object_or_404(Student.objects.prefetch_related('events'), id=student_id, is_deleted=False)
        
        # Get transaction details from SSL Commerz
        if request.method == 'POST':
            post_data = request.POST
            tran_id = post_data.get('tran_id')
            val_id = post_data.get('val_id')
            amount = post_data.get('amount')
            card_type = post_data.get('card_type', '')
            registration_id = post_data.get('value_a', '')
            received_hash = post_data.get('value_b', '')
            callback_data = dict(request.POST.items())
        else:
            get_data = request.GET
            tran_id = get_data.get('tran_id')
            val_id = get_data.get('val_id')
            amount = get_data.get('amount')
            card_type = get_data.get('card_type', '')
            registration_id = get_data.get('value_a', '')
            received_hash = get_data.get('value_b', '')
            callback_data = dict(request.GET.items())

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
        
        # Verify integrity of the callback - Fixed hash comparison
        if registration_id != str(student.id):  # Compare with student.id instead of registration_id
            log_security_alert(
                'PAYMENT_FRAUD',
                'Student ID mismatch in payment success callback',
                ip_address,
                user_agent,
                student=student,
                payment=payment,
                data={'expected': str(student.id), 'received': registration_id}
            )
            messages.error(request, 'Invalid payment transaction.')
            return redirect('home')

        # Verify security hash - Fixed hash generation and comparison
        expected_hash = hashlib.sha256(f"{tran_id}{student.id}{payment.amount}".encode()).hexdigest()
        if not hmac.compare_digest(expected_hash, received_hash):
            log_security_alert(
                'PAYMENT_FRAUD',
                'Payment hash mismatch in payment success callback',
                ip_address,
                user_agent,
                student=student,
                payment=payment,
                data={'expected': expected_hash, 'received': received_hash}
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
        
        # Final verification checks
        if (validation_result.get('status') in ['VALID', 'VALIDATED'] and 
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

@csrf_exempt
@ratelimit(key='ip', rate='10/m', method=['GET', 'POST'])
def payment_fail(request, student_id):
    """
    Handle failed payment with detailed error information
    """
    try:
        student = get_object_or_404(Student, id=student_id, is_deleted=False)
        
        # Get transaction details from URL parameters
        if request.method == 'POST':
            post_data = request.POST
            tran_id = post_data.get('tran_id')
            error_code = post_data.get('error')
            failed_reason = post_data.get('failedreason', '')
        else:
            get_data = request.GET
            tran_id = get_data.get('tran_id')
            error_code = get_data.get('error')
            failed_reason = get_data.get('failedreason', '')
        
        # Map common SSLCommerz error codes to user-friendly messages
        error_messages = {
            'FAILED': 'Your payment could not be processed. Please try again.',
            'CANCELLED': 'Payment was cancelled by user.',
            'UNATTEMPTED': 'Payment was not attempted.',
            'EXPIRED': 'Payment session has expired. Please try again.',
            'INCOMPLETE': 'Payment process was incomplete.',
            'INVALID_TRANSACTION': 'Invalid transaction. Please start over.',
            'AMOUNT_MISMATCH': 'Payment amount mismatch detected.',
            'CARD_DECLINED': 'Your card was declined. Please try a different payment method.',
            'INSUFFICIENT_FUNDS': 'Insufficient funds in your account.',
            'NETWORK_ERROR': 'Network error occurred. Please check your connection and try again.',
            'BANK_DECLINE': 'Transaction was declined by your bank.',
            'INVALID_CARD': 'Invalid card information provided.',
            'CARD_EXPIRED': 'Your card has expired.',
            'PROCESSING_ERROR': 'Payment processing error. Please try again later.',
        }
        
        # Determine error message
        error_message = None
        if error_code:
            error_message = error_messages.get(error_code.upper(), f"Payment failed: {error_code}")
        elif failed_reason:
            error_message = f"Payment failed: {failed_reason}"
        else:
            error_message = "Payment could not be completed. Please try again."
        
        # Update payment status if transaction ID exists
        if tran_id:
            try:
                payment = Payment.objects.get(transaction_id=tran_id, student=student)
                payment.status = 'FAILED'
                payment.gateway_response = {
                    'error_code': error_code,
                    'failed_reason': failed_reason,
                    'callback_data': dict(request.GET.items())
                }
                payment.save()
                
                logger.warning(f'Payment failed for student {student.id}, transaction {tran_id}, error: {error_code}')
                
                # Log security alert for suspicious patterns
                if error_code in ['AMOUNT_MISMATCH', 'INVALID_TRANSACTION']:
                    log_security_alert(
                        'PAYMENT_FRAUD',
                        f'Suspicious payment failure: {error_code}',
                        get_client_ip(request),
                        request.META.get('HTTP_USER_AGENT', ''),
                        student=student,
                        payment=payment,
                        data={'error_code': error_code, 'failed_reason': failed_reason}
                    )
                
            except Payment.DoesNotExist:
                logger.error(f'Payment record not found for transaction {tran_id}')
        
        context = {
            'student': student,
            'error_message': error_message,
            'error_code': error_code,
            'transaction_id': tran_id,
            'can_retry': error_code not in ['AMOUNT_MISMATCH', 'INVALID_TRANSACTION'],  # Don't allow retry for suspicious errors
        }
        return render(request, 'registration/payment_fail.html', context)
        
    except Exception as e:
        logger.error(f'Payment fail handler error: {e}')
        messages.error(request, 'An error occurred while processing the payment failure.')
        return redirect('home')

@csrf_exempt
@ratelimit(key='ip', rate='10/m', method=['GET', 'POST'])
def payment_cancel(request, student_id):
    """
    Handle cancelled payment with user guidance
    """
    try:
        student = get_object_or_404(Student, id=student_id, is_deleted=False)
        
        # Get transaction details
        if request.method == 'POST':
            post_data = request.POST
            tran_id = post_data.get('tran_id')
            cancel_reason = post_data.get('cancel_reason', 'User cancelled the payment')
        else:
            get_data = request.GET
            tran_id = get_data.get('tran_id')
            cancel_reason = get_data.get('cancel_reason', 'User cancelled the payment')
        
        # Update payment status if exists
        if tran_id:
            try:
                payment = Payment.objects.get(transaction_id=tran_id, student=student)
                payment.status = 'CANCELLED'
                payment.gateway_response = {
                    'cancel_reason': cancel_reason,
                    'callback_data': dict(request.GET.items())
                }
                payment.save()
                
                logger.info(f'Payment cancelled for student {student.id}, transaction {tran_id}')
            except Payment.DoesNotExist:
                logger.warning(f'Payment record not found for cancelled transaction {tran_id}')
        
        context = {
            'student': student,
            'transaction_id': tran_id,
            'cancel_reason': cancel_reason,
        }
        return render(request, 'registration/payment_cancel.html', context)
        
    except Exception as e:
        logger.error(f'Payment cancel handler error: {e}')
        messages.error(request, 'An error occurred.')
        return redirect('home')
    
def handle_payment_timeout(request):
    """
    Handle payment session timeout
    """
    student_id = request.GET.get('student_id')
    tran_id = request.GET.get('tran_id')
    
    if student_id and tran_id:
        try:
            student = Student.objects.get(id=student_id, is_deleted=False)
            payment = Payment.objects.get(transaction_id=tran_id, student=student)
            
            # Mark payment as expired
            payment.status = 'EXPIRED'
            payment.gateway_response = {'timeout_reason': 'Payment session expired'}
            payment.save()
            
            messages.warning(request, 'Your payment session has expired. Please try again.')
            return redirect('payment_gateway', student_id=student.id)
            
        except (Student.DoesNotExist, Payment.DoesNotExist):
            pass
    
    messages.error(request, 'Payment session expired.')
    return redirect('home')

def check_payment_status(request, student_id, transaction_id):
    """
    Manual payment status check endpoint for uncertain cases
    """
    try:
        student = get_object_or_404(Student, id=student_id, is_deleted=False)
        payment = get_object_or_404(Payment, transaction_id=transaction_id, student=student)
        
        # Re-validate with SSLCommerz
        if payment.status == 'PENDING':
            sslcommerz = SSLCOMMERZ()
            validation_data = {
                'val_id': request.GET.get('val_id'),
                'store_id': settings.SSLCOMMERZ_STORE_ID,
                'store_passwd': settings.SSLCOMMERZ_STORE_PASSWORD,
                'format': 'json'
            }
            
            try:
                validation_url = ('https://sandbox.sslcommerz.com/validator/api/validationserverAPI.php' 
                                 if settings.SSLCOMMERZ_IS_SANDBOX 
                                 else 'https://securepay.sslcommerz.com/validator/api/validationserverAPI.php')
                
                response = requests.get(validation_url, params=validation_data, timeout=30)
                response.raise_for_status()
                result = response.json()
                
                if result.get('status') in ['VALID', 'VALIDATED']:
                    # Update payment as successful
                    with transaction.atomic():
                        payment.status = 'SUCCESS'
                        payment.gateway_response = result
                        payment.completed_at = timezone.now()
                        payment.save()
                        
                        student.is_paid = True
                        student.payment_verified = True
                        student.save()
                    
                    messages.success(request, 'Payment verification successful!')
                    return redirect('payment_success', student_id=student.id)
                else:
                    messages.error(request, 'Payment verification failed.')
                    return redirect('payment_fail', student_id=student.id)
                    
            except requests.exceptions.RequestException as e:
                logger.error(f'Payment status check error: {e}')
                messages.error(request, 'Unable to verify payment status. Please contact support.')
        
        # Return current status
        if payment.status == 'SUCCESS':
            return redirect('payment_success', student_id=student.id)
        elif payment.status in ['FAILED', 'EXPIRED']:
            return redirect('payment_fail', student_id=student.id)
        elif payment.status == 'CANCELLED':
            return redirect('payment_cancel', student_id=student.id)
        else:
            messages.info(request, f'Payment status: {payment.get_status_display()}')
            return redirect('home')
            
    except Exception as e:
        logger.error(f'Payment status check error: {e}')
        messages.error(request, 'Error checking payment status.')
        return redirect('home')
    
# Middleware function to handle expired payments automatically
def cleanup_expired_payments():
    """
    Cleanup expired payments - can be called via cron job or management command
    """
    try:
        expired_payments = Payment.objects.filter(
            status='PENDING',
            expires_at__lt=timezone.now()
        )
        
        count = 0
        for payment in expired_payments:
            payment.status = 'EXPIRED'
            payment.save()
            count += 1
        
        if count > 0:
            logger.info(f'Marked {count} payments as expired')
        
        return count
        
    except Exception as e:
        logger.error(f'Error cleaning up expired payments: {e}')
        return 0


@csrf_exempt
@require_POST
@ratelimit(key='ip', rate='30/m', method='POST')
def payment_ipn(request):
    """
    Handle SSL Commerz IPN (Instant Payment Notification) with enhanced security.
    This view uses a direct Validation API call to ensure authenticity and checks
    for transaction risk levels before marking a payment as successful.
    """
    ip_address = get_client_ip(request)
    user_agent = request.META.get('HTTP_USER_AGENT', '')
    
    logger.info(f"IPN received from {ip_address}")

    try:
        ipn_data = request.POST.dict()
        tran_id = ipn_data.get('tran_id')

        if not tran_id:
            logger.error("IPN received without a transaction ID.")
            return HttpResponseBadRequest('Transaction ID missing.')

        logger.info(f"IPN data for tran_id {tran_id}: {ipn_data}")

        # 1. Validate the IPN using the Validation API for maximum security
        sslcz = SSLCOMMERZ()
        is_valid, validation_response = sslcz.validate_ipn(ipn_data)

        if not is_valid:
            log_security_alert('INVALID_HASH', 'IPN validation failed via API call', ip_address, user_agent, data=ipn_data)
            logger.warning(f"IPN validation failed for tran_id: {tran_id}. Reason: {validation_response.get('failed_reason')}")
            return HttpResponseBadRequest('Invalid IPN')

        # 2. Retrieve the payment record
        try:
            payment = Payment.objects.get(transaction_id=tran_id)
        except Payment.DoesNotExist:
            log_security_alert('PAYMENT_FRAUD', f'IPN for non-existent transaction: {tran_id}', ip_address, user_agent, data=ipn_data)
            logger.warning(f"IPN received for non-existent tran_id: {tran_id}")
            return HttpResponseBadRequest('Transaction not found')

        # 3. Idempotency Check: If payment is already successful, do nothing.
        if payment.status == 'SUCCESS':
            logger.info(f"IPN for already successful payment {tran_id} received. Skipping.")
            return HttpResponse('OK', status=200)

        # 4. Verify the payment amount
        if not verify_payment_amount(payment.amount, validation_response.get('amount')):
            log_security_alert('PAYMENT_FRAUD', f"IPN amount mismatch - Expected: {payment.amount}, Received: {validation_response.get('amount')}", ip_address, user_agent, payment=payment, data=ipn_data)
            logger.warning(f"IPN amount mismatch for tran_id: {tran_id}")
            return HttpResponseBadRequest('Amount mismatch')

        # 5. Process the IPN based on the validated status and risk level
        with transaction.atomic():
            status = validation_response.get('status')
            risk_level = validation_response.get('risk_level')
            val_id = validation_response.get('val_id')

            if status == 'VALID':
                # Check risk level
                if risk_level == '0':
                    # Low risk, mark as successful
                    payment.status = 'SUCCESS'
                    payment.gateway_txnid = val_id
                    payment.gateway_response = validation_response
                    payment.completed_at = timezone.now()
                    payment.save()

                    student = payment.student
                    student.is_paid = True
                    student.payment_verified = True
                    student.save()

                    logger.info(f'Payment for tran_id {tran_id} successfully updated to SUCCESS via IPN.')

                    receipt, created = Receipt.objects.get_or_create(student=student, payment=payment)
                    if not receipt.email_sent:
                        send_registration_email(student, receipt)
                
                else: # High risk
                    payment.gateway_response = validation_response
                    payment.save()
                    log_security_alert(
                        'HIGH_RISK_TRANSACTION',
                        f'High-risk transaction detected for tran_id: {tran_id}. Needs manual review.',
                        ip_address,
                        user_agent,
                        payment=payment,
                        data=validation_response
                    )
                    logger.warning(f"High-risk transaction {tran_id} flagged for manual review.")

            elif status in ['FAILED', 'CANCELLED', 'EXPIRED']:
                payment.status = status
                payment.gateway_response = validation_response
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

def events_page(request):
    """
    Dedicated page to list all events.
    """
    events = Event.objects.filter(is_active=True).order_by('-created_at')
    context = {
        'events': events,
    }
    return render(request, 'registration/events_page.html', context)

def about_us(request):
    """
    About Us page with moderators, board members, and past event images.
    """
    moderators = TeamMemberProfile.objects.filter(member_type='MODERATOR')
    board_members = TeamMemberProfile.objects.filter(member_type='BOARD_MEMBER')
    past_event_images = PastEventImage.objects.all()
    context = {
        'moderators': moderators,
        'board_members': board_members,
        'past_event_images': past_event_images,
    }
    return render(request, 'registration/about_us.html', context)

def join_us(request):
    """
    Join Us page with links to social media.
    """
    social_media_profiles = SocialMediaProfile.objects.filter(is_active=True)
    context = {
        'social_media_profiles': social_media_profiles,
    }
    return render(request, 'registration/join_us.html', context)

