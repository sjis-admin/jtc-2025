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
from django.db import transaction, models
from django.db.models import Min, Exists, OuterRef, Subquery
from django.urls import reverse
from django.contrib.admin.views.decorators import staff_member_required 
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

from .models import (Student, Event, EventOption, Payment, Receipt, 
                    StudentEventRegistration, PaymentAttempt, School, Grade,
                    Team, TeamMember, Countdown, HomePageAsset, SocialMediaProfile,
                    TeamMemberProfile, PastEventImage, ValorantBackgroundVideo)
from .forms import StudentRegistrationForm
from .sslcommerz import SSLCOMMERZ


def home(request):
    """
    Home page with event listing and security monitoring
    """
    # Check for suspicious activity
    ip_address = get_client_ip(request)
    user_agent = request.META.get('HTTP_USER_AGENT', '')
    
    try:
        individual_options = EventOption.objects.filter(event=OuterRef('pk'), event_type='INDIVIDUAL')
        team_options = EventOption.objects.filter(event=OuterRef('pk'), event_type='TEAM')

        # Subqueries to get individual and team fees
        individual_fee_subquery = EventOption.objects.filter(
            event=OuterRef('pk'),
            event_type='INDIVIDUAL'
        ).values('fee')[:1]

        team_fee_subquery = EventOption.objects.filter(
            event=OuterRef('pk'),
            event_type='TEAM'
        ).values('fee')[:1]

        active_events = Event.objects.filter(is_active=True).annotate(
            min_fee=Min('options__fee'),
            has_individual=Exists(individual_options),
            has_team=Exists(team_options),
            individual_fee=Subquery(individual_fee_subquery, output_field=models.DecimalField()),
            team_fee=Subquery(team_fee_subquery, output_field=models.DecimalField())
        ).order_by('created_at')
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

def student_registration(request):
    ip_address = get_client_ip(request)
    if request.method == 'POST':
        form = StudentRegistrationForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    # --- Step 1: Get or Create Student ---
                    student, _ = Student.objects.update_or_create(
                        email=form.cleaned_data['email'],
                        defaults={
                            'name': form.cleaned_data['name'],
                            'school_college': form.cleaned_data.get('school_college'),
                            'other_school': form.cleaned_data.get('other_school'),
                            'grade': form.cleaned_data['grade'],
                            'section': form.cleaned_data.get('section'),
                            'roll': form.cleaned_data['roll'],
                            'mobile_number': form.cleaned_data['mobile_number'],
                            'registration_ip': ip_address,
                        }
                    )

                    event_options = form.cleaned_data['selected_events']
                    
                    # --- Step 2: Create a PENDING Payment object ---
                    subtotal = sum(o.fee for o in event_options)
                    fee_percentage = Decimal(getattr(settings, 'SSLCOMMERZ_FEE_PERCENTAGE', '0.015'))
                    fee = (subtotal * fee_percentage).quantize(Decimal('0.01'))
                    total_amount = subtotal + fee

                    if total_amount <= 0:
                        messages.error(request, "You must select at least one event with a fee.")
                        return redirect('register')

                    payment = Payment.objects.create(
                        student=student,
                        amount=total_amount,
                        client_ip=ip_address,
                        transaction_id=generate_secure_transaction_id() # Ensure this function exists and is imported
                    )
                    payment.save()

                    # --- Step 3: Create Event Registrations linked to the Payment ---
                    for option in event_options:
                        reg = StudentEventRegistration.objects.create(
                            student=student,
                            event_option=option,
                            payment=payment,
                            registration_ip=ip_address
                        )
                        # --- Handle Team Creation ---
                        if option.event_type == 'TEAM':
                            team_name = request.POST.get(f'team_name_{option.id}', '').strip()
                            if not team_name:
                                raise ValueError(f"Team name is required for {option.event.name}")
                            
                            team = Team.objects.create(name=team_name, registration=reg)
                            leader_index = request.POST.get(f'team_leader_{option.id}', '0')
                            
                            TeamMember.objects.create(team=team, name=student.name, is_leader=(leader_index == '0'))
                            
                            for i in range(1, option.max_team_size or 2):
                                member_name = request.POST.get(f'team_member_{option.id}_{i}', '').strip()
                                if member_name:
                                    TeamMember.objects.create(team=team, name=member_name, is_leader=(leader_index == str(i)))

                # --- Step 4: Redirect to Payment Gateway ---
                return redirect('payment_gateway', payment_id=payment.id)

            except Exception as e:
                logger.error(f'Error during registration processing: {e}', exc_info=True)
                messages.error(request, f'An unexpected error occurred: {e}')
                return render(request, 'registration/register.html', {'form': form})
        else:
            logger.error(f"Form validation failed: {form.errors}")
            messages.error(request, 'Please correct the errors below.')
    else:
        form = StudentRegistrationForm()

    return render(request, 'registration/register.html', {'form': form})


# Updated get_events_for_grade view in views.py
@require_GET
def get_events_for_grade(request):
    grade_id = request.GET.get('grade')
    
    if not grade_id:
        # Return empty state when no grade is selected
        context = {
            'events': [],
            'show_no_grade_message': True,
        }
        return render(request, 'registration/_event_list.html', context)
    
    try:
        grade = Grade.objects.get(id=grade_id)
        # Get events that include this grade in their target_grades
        events = Event.objects.filter(
            target_grades__id=grade_id, 
            is_active=True
        ).distinct().prefetch_related('options', 'target_grades')
        
        logger.info(f"Grade {grade.name} selected - Found {events.count()} events")
        
        context = {
            'events': events,
            'selected_grade': grade,
            'show_no_events_message': events.count() == 0,
        }
        
        return render(request, 'registration/_event_list.html', context)
        
    except Grade.DoesNotExist:
        logger.warning(f"Invalid grade ID requested: {grade_id}")
        context = {
            'events': [],
            'show_error_message': True,
        }
        return render(request, 'registration/_event_list.html', context)
    except Exception as e:
        logger.error(f"Error in get_events_for_grade: {e}")
        context = {
            'events': [],
            'show_error_message': True,
        }
        return render(request, 'registration/_event_list.html', context)

@require_GET
def get_group_for_grade(request):
    """
    Calculates the group for a given grade ID using the grade's 'order' field.
    This is an HTMX endpoint that returns a partial HTML template.
    """
    grade_id = request.GET.get('grade')
    
    if not grade_id:
        context = {
            'group_display': 'Select grade first',
            'css_classes': 'w-full px-4 py-2 border border-gray-300 rounded-lg bg-gray-50 text-gray-500'
        }
        return render(request, 'registration/_group_display.html', context)
    
    try:
        grade = Grade.objects.get(id=grade_id)
        group = Student.calculate_group_from_grade_id(grade_id)
        
        if group is None:
            # Grade is outside the defined groups
            context = {
                'group_display': 'Not applicable for this grade',
                'css_classes': 'w-full px-4 py-2 border border-gray-300 rounded-lg bg-gray-50 text-gray-500'
            }
            return render(request, 'registration/_group_display.html', context)

        group_display = dict(Student.GROUP_CHOICES).get(group, '')
        
        logger.info(f"Grade '{grade.name}' (order: {grade.order}) mapped to group {group}: {group_display}")
        
        context = {
            'group_display': group_display,
            'css_classes': 'w-full px-4 py-2 border border-green-300 rounded-lg bg-green-50 text-green-700 font-medium'
        }
        return render(request, 'registration/_group_display.html', context)
        
    except Grade.DoesNotExist:
        logger.warning(f"Invalid grade ID requested: {grade_id}")
        context = {
            'group_display': 'Invalid grade',
            'css_classes': 'w-full px-4 py-2 border border-red-300 rounded-lg bg-red-50 text-red-600'
        }
        return render(request, 'registration/_group_display.html', context)
        
    except Exception as e:
        logger.error(f"Unexpected error in get_group_for_grade: {e}")
        context = {
            'group_display': 'Error',
            'css_classes': 'w-full px-4 py-2 border border-red-300 rounded-lg bg-red-50 text-red-600'
        }
        return render(request, 'registration/_group_display.html', context)

@require_GET
def validate_grade(request):
    """Validate grade selection and return status"""
    grade_id = request.GET.get('grade')
    
    if not grade_id:
        return JsonResponse({
            'valid': False,
            'message': 'No grade selected'
        })
    
    try:
        grade = Grade.objects.get(id=grade_id)
        group = Student.calculate_group_from_grade(grade.name)
        group_display = dict(Student.GROUP_CHOICES).get(group, '')
        
        return JsonResponse({
            'valid': True,
            'grade_name': grade.name,
            'group': group,
            'group_display': group_display,
            'message': 'Valid grade selection'
        })
    except Grade.DoesNotExist:
        return JsonResponse({
            'valid': False,
            'message': 'Invalid grade selection'
        })
    except Exception as e:
        logger.error(f"Error validating grade {grade_id}: {e}")
        return JsonResponse({
            'valid': False,
            'message': 'Error validating grade'
        })
    
@require_GET  
def check_event_availability(request):
    """Check if events are available for selected grade"""
    grade_id = request.GET.get('grade')
    
    if not grade_id:
        return JsonResponse({
            'available': False,
            'count': 0,
            'message': 'No grade selected'
        })
    
    try:
        grade = Grade.objects.get(id=grade_id)
        events = Event.objects.filter(
            target_grades__id=grade_id, 
            is_active=True
        ).prefetch_related('options')
        
        event_count = events.count()
        
        return JsonResponse({
            'available': event_count > 0,
            'count': event_count,
            'message': f'{event_count} events available for {grade.name}' if event_count > 0 else 'No events available for this grade'
        })
        
    except Grade.DoesNotExist:
        return JsonResponse({
            'available': False,
            'count': 0,
            'message': 'Invalid grade selection'
        })
    except Exception as e:
        logger.error(f"Error checking event availability for grade {grade_id}: {e}")
        return JsonResponse({
            'available': False,
            'count': 0,
            'message': 'Error checking event availability'
        })
    
@require_POST
def calculate_total(request):
    """
    HTMX endpoint to calculate total amount, including SSLCommerz fee.
    """
    try:
        selected_events_str = request.POST.get('selected_events', '')
        if not selected_events_str:
            return render(request, 'registration/_total_display.html', {'subtotal': 0, 'fee': 0, 'total': 0})

        event_option_ids = [int(id) for id in selected_events_str.split(',') if id.isdigit()]
        event_options = EventOption.objects.filter(id__in=event_option_ids, event__is_active=True)

        subtotal = sum(option.fee for option in event_options)
        
        # Calculate SSLCommerz fee (e.g., 1.5%)
        fee_percentage = Decimal(getattr(settings, 'SSLCOMMERZ_FEE_PERCENTAGE', '0.015'))
        fee = (subtotal * fee_percentage).quantize(Decimal('0.01'))
        total = subtotal + fee

        context = {
            'subtotal': subtotal,
            'fee': fee,
            'total': total,
        }
        return render(request, 'registration/_total_display.html', context)

    except Exception as e:
        logger.error(f'Error calculating total: {e}')
        return HttpResponse('<div class="text-red-500">Error</div>', status=500)

@require_GET
def get_team_section(request):
    option_id = request.GET.get('option_id')
    try:
        option = EventOption.objects.get(id=option_id)
        if option.event_type == 'TEAM':
            return render(request, 'registration/_team_section.html', {'option': option})
        else:
            return HttpResponse('') # Return empty response for individual events
    except EventOption.DoesNotExist:
        return HttpResponse('')


def payment_gateway(request, payment_id):
    try:
        payment = get_object_or_404(Payment, id=payment_id, status='PENDING')
        student = payment.student

        sslcommerz = SSLCOMMERZ()
        response_data = sslcommerz.create_session(
            amount=payment.amount,
            tran_id=payment.transaction_id,
            cust_name=student.name,
            cust_email=student.email,
            cust_phone=student.mobile_number,
            payment_id=payment.id,
            cus_add1=student.school_college.name if student.school_college else student.other_school,
            cus_city='Dhaka',
            cus_state='Dhaka',
            cus_postcode='1000',
            cus_country='Bangladesh'
        )

        if response_data.get('status') == 'SUCCESS':
            payment.sessionkey = response_data.get('sessionkey', '')
            payment.save()
            return redirect(response_data.get('GatewayPageURL'))
        else:
            raise ValueError(response_data.get('failedreason', 'Gateway initialization failed.'))

    except Payment.DoesNotExist:
        messages.error(request, "This payment session is invalid or has expired.")
        return redirect('register')
    except Exception as e:
        logger.error(f'Payment gateway error for payment {payment_id}: {e}', exc_info=True)
        messages.error(request, f'Could not initiate payment: {e}')
        return redirect('register')

@csrf_exempt
def payment_success(request):
    post_data = request.POST
    tran_id = post_data.get('tran_id')

    if not tran_id:
        return HttpResponseBadRequest("Invalid request: Missing transaction ID.")

    try:
        payment = Payment.objects.get(transaction_id=tran_id)
    except Payment.DoesNotExist:
        logger.error(f"Payment success callback for non-existent transaction: {tran_id}")
        return HttpResponseBadRequest("Invalid Transaction.")

    if payment.status == 'SUCCESS':
        messages.info(request, "This payment has already been processed.")
        receipt = Receipt.objects.get(payment=payment)
        
        # Get event registrations with proper event names
        event_registrations = StudentEventRegistration.objects.filter(
            student=payment.student,
            payment=payment
        ).select_related('event_option__event')
        
        context = {
            'student': payment.student,
            'payment': payment,
            'receipt': receipt,
            'event_registrations': event_registrations,
        }
        return render(request, 'registration/payment_success.html', context)

    sslcz = SSLCOMMERZ()
    is_valid, validation_data = sslcz.validate_ipn(post_data)

    if is_valid and validation_data.get('status') in ['VALID', 'VALIDATED']:
        if payment.amount == Decimal(validation_data.get('amount')):
            with transaction.atomic():
                payment.status = 'SUCCESS'
                payment.payment_method = validation_data.get('card_type', '')
                payment.gateway_txnid = validation_data.get('val_id')
                payment.gateway_response = validation_data
                payment.completed_at = timezone.now()
                payment.save()

                student = payment.student
                student.is_paid = True
                student.payment_verified = True
                student.save()

                receipt = Receipt.objects.create(student=student, payment=payment)
                send_registration_email(student, receipt)

            # Get event registrations with proper event names
            event_registrations = StudentEventRegistration.objects.filter(
                student=student,
                payment=payment
            ).select_related('event_option__event')

            context = {
                'student': student,
                'payment': payment,
                'receipt': receipt,
                'event_registrations': event_registrations,
            }

            messages.success(request, "Registration and payment successful!")
            return render(request, 'registration/payment_success.html', context)
        else:
            payment.status = 'FAILED'
            payment.save()
            logger.error(f"Payment validation failed for {tran_id}: Amount mismatch.")
            return HttpResponseBadRequest("Payment validation failed: Amount mismatch.")
    else:
        payment.status = 'FAILED'
        payment.save()
        logger.error(f"Payment validation failed for {tran_id}: Invalid data from SSLCommerz.")
        return HttpResponseBadRequest("Payment validation failed.")

@staff_member_required
def generate_receipt(request, student_id):
    """Generate receipt for a student - Updated with standalone template"""
    student = get_object_or_404(Student, id=student_id)
    
    if not student.is_paid:
        messages.error(request, 'Cannot generate receipt for unpaid registration.')
        return redirect('admin_student_detail', student_id=student.id)
    
    payment = student.payments.filter(status='SUCCESS').first()
    if not payment:
        messages.error(request, 'No successful payment found.')
        return redirect('admin_student_detail', student_id=student.id)
    
    # Create or get existing receipt
    receipt, created = Receipt.objects.get_or_create(
        student=student,
        payment=payment,
        defaults={'generated_by': request.user}
    )
    
    if created:
        log_admin_action(
            user=request.user,
            action='RECEIPT_GENERATE',
            model_name='Receipt',
            object_id=str(receipt.id),
            description=f'Receipt generated for {student.name}',
            ip_address=get_client_ip(request)
        )
    
    # Use standalone template for printing
    context = {
        'student': student,
        'receipt': receipt,
        'payment': payment,
    }
    
    return render(request, 'registration/receipt_standalone.html', context)

def receipt_print_view(request, receipt_number):
    """Dedicated view for printing receipts without header"""
    receipt = get_object_or_404(Receipt, receipt_number=receipt_number)
    
    context = {
        'student': receipt.student,
        'receipt': receipt,
        'payment': receipt.payment,
    }
    
    return render(request, 'registration/receipt_standalone.html', context)

@csrf_exempt
def payment_fail(request, payment_id):
    """
    Handle failed payment with detailed error information
    """
    try:
        payment = get_object_or_404(Payment, id=payment_id)
        student = payment.student
        
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
            'payment': payment,
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

def payment_cancel(request, payment_id):
    """
    Handle cancelled payment with user guidance
    """
    try:
        payment = get_object_or_404(Payment, id=payment_id)
        student = payment.student
        
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
            'payment': payment,
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
    Enhanced events page with modern UI and comprehensive event details
    """
    ip_address = get_client_ip(request)
    user_agent = request.META.get('HTTP_USER_AGENT', '')
    
    try:
        # Subqueries to get individual and team fees
        individual_fee_subquery = EventOption.objects.filter(
            event=OuterRef('pk'),
            event_type='INDIVIDUAL'
        ).values('fee')[:1]

        team_fee_subquery = EventOption.objects.filter(
            event=OuterRef('pk'),
            event_type='TEAM'
        ).values('fee')[:1]

        # Get active events with related data - FIXED to work with your model structure
        events = Event.objects.filter(is_active=True).prefetch_related('options').annotate(
            individual_fee=Subquery(individual_fee_subquery, output_field=models.DecimalField()),
            team_fee=Subquery(team_fee_subquery, output_field=models.DecimalField())
        ).order_by('-created_at')
        
        # Prepare event data for frontend - FIXED to match your model structure
        events_data = []
        for event in events:
            # Get registration count - FIXED to work with your through model
            registration_count = StudentEventRegistration.objects.filter(
                event_option__event=event
            ).count()

            # Format fee display from annotated fields
            individual_fee = event.individual_fee
            team_fee = event.team_fee
            fee_display = "N/A"

            if individual_fee is not None and team_fee is not None:
                if individual_fee == team_fee:
                    fee_display = f"৳{individual_fee:,.0f}"
                else:
                    fee_display = f"৳{individual_fee:,.0f} / ৳{team_fee:,.0f}"
            elif individual_fee is not None:
                fee_display = f"৳{individual_fee:,.0f}"
            elif team_fee is not None:
                fee_display = f"৳{team_fee:,.0f}"
            else:
                # Fallback if no options are found (or they are free)
                min_fee_agg = event.options.aggregate(min_fee=models.Min('fee'))
                min_fee = min_fee_agg.get('min_fee')
                if min_fee is not None and min_fee > 0:
                    fee_display = f"৳{min_fee:,.0f}"
                elif min_fee == 0:
                    fee_display = "Free"

            event_data = {
                'id': event.id,
                'name': event.name,
                'description': event.description,
                'fee': fee_display,  # Using the new formatted fee display
                'created_at': event.created_at,
                'rules_type': event.rules_type,
                'rules_text': event.rules_text,
                'rules_file_url': event.rules_file.url if event.rules_file else '',
                'event_image_url': event.event_image.url if event.event_image else '',
                'registration_count': registration_count,
                'has_individual': event.options.filter(event_type='INDIVIDUAL').exists(),
                'has_team': event.options.filter(event_type='TEAM').exists(),
                'options': list(event.options.all().values('id', 'name', 'event_type', 'fee', 'max_team_size', 'max_participants'))
            }
            events_data.append(event_data)
        
        # Log page access for analytics
        logger.info(f'Events page accessed from {ip_address} - {len(events_data)} events displayed')
        
        context = {
            'events': events,
            'events_data': events_data,
            'events_count': len(events_data),
        }
        
        return render(request, 'registration/events_page.html', context)
        
    except Exception as e:
        logger.error(f'Error in events_page view: {e}', exc_info=True)
        messages.error(request, 'An error occurred while loading events. Please try again.')
        
        # Return empty context on error
        context = {
            'events': [],
            'events_data': [],
            'events_count': 0,
        }
        return render(request, 'registration/events_page.html', context)
    
def event_rules_api(request, event_id):
    """
    API endpoint to fetch event rules dynamically
    Used for AJAX loading of rules content
    """
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        event = get_object_or_404(
            Event.objects.filter(is_active=True), 
            id=event_id
        )
        
        # Prepare rules data based on type
        rules_data = {
            'id': event.id,
            'name': event.name,
            'rules_type': event.rules_type,
        }
        
        if event.rules_type == 'TEXT':
            rules_data['content'] = event.rules_text or 'No rules specified for this event.'
        elif event.rules_type == 'IMAGE':
            rules_data['content'] = event.rules_file.url if event.rules_file else ''
        elif event.rules_type == 'PDF':
            rules_data['content'] = event.rules_file.url if event.rules_file else ''
        else:
            rules_data['content'] = 'Rules will be updated soon.'
        
        # Log API access
        logger.info(f'Event rules API accessed for event {event_id} from {get_client_ip(request)}')
        
        return JsonResponse({
            'success': True,
            'data': rules_data
        })
        
    except Event.DoesNotExist:
        logger.warning(f'Event rules API called for non-existent event: {event_id}')
        return JsonResponse({
            'success': False,
            'error': 'Event not found'
        }, status=404)
    except Exception as e:
        logger.error(f'Error in event_rules_api: {e}')
        return JsonResponse({
            'success': False,
            'error': 'An error occurred while fetching event rules'
        }, status=500)

def event_details_api(request, event_id):
    """
    API endpoint to fetch detailed event information
    Can be used for enhanced modals or event detail pages
    """
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        event = get_object_or_404(
            Event.objects.select_related().prefetch_related('studenteventregistration_set'), 
            id=event_id, 
            is_active=True
        )
        
        # Get registration statistics
        registration_count = event.get_registration_count()
        
        # Calculate registration progress percentage
        registration_progress = 0
        if event.max_participants:
            registration_progress = min((registration_count / event.max_participants) * 100, 100)
        
        event_data = {
            'id': event.id,
            'name': event.name,
            'description': event.description,
            'fee': str(event.fee),
            'event_type': event.event_type,
            'event_type_display': event.get_event_type_display(),
            'max_team_size': event.max_team_size,
            'max_participants': event.max_participants,
            'registration_count': registration_count,
            'registration_progress': registration_progress,
            'is_registration_full': event.is_registration_full(),
            'created_at': event.created_at.isoformat(),
            'updated_at': event.updated_at.isoformat(),
            'event_image_url': event.event_image.url if event.event_image else '',
            'rules_type': event.rules_type,
            'has_rules': bool(event.rules_text or event.rules_file),
        }
        
        return JsonResponse({
            'success': True,
            'data': event_data
        })
        
    except Event.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Event not found'
        }, status=404)
    except Exception as e:
        logger.error(f'Error in event_details_api: {e}')
        return JsonResponse({
            'success': False,
            'error': 'An error occurred while fetching event details'
        }, status=500)






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

def valorant_page(request):
    video = ValorantBackgroundVideo.objects.filter(is_active=True).first()
    context = {
        'video': video,
    }
    return render(request, 'registration/valorant.html', context)



@csrf_exempt
def debug_form_submission(request):
    """Temporary debug view to see what's being submitted"""
    if request.method == 'POST':
        logger.info("=== FORM SUBMISSION DEBUG ===")
        logger.info(f"POST data keys: {list(request.POST.keys())}")
        logger.info(f"POST data: {dict(request.POST)}")
        logger.info(f"selected_events value: '{request.POST.get('selected_events')}'")
        logger.info(f"events list: {request.POST.getlist('events')}")
        
        # Try to create form and see validation errors
        form = StudentRegistrationForm(request.POST)
        logger.info(f"Form is_valid: {form.is_valid()}")
        if not form.is_valid():
            logger.error(f"Form errors: {form.errors}")
            logger.error(f"Form non_field_errors: {form.non_field_errors()}")
            
            # Specifically check selected_events field
            try:
                selected_events_data = form.cleaned_data.get('selected_events', 'NOT_FOUND')
                logger.info(f"Cleaned selected_events: {selected_events_data}")
            except:
                logger.error("Could not get cleaned_data for selected_events")
        
        logger.info("=== END DEBUG ===")
    
    return JsonResponse({'debug': 'complete'})


@csrf_exempt
def test_form_submission(request):
    """Simple test to isolate the form validation issue"""
    if request.method == 'POST':
        logger.info("=== TEST FORM SUBMISSION ===")
        
        # Log all POST data
        for key, value in request.POST.items():
            logger.info(f"POST['{key}'] = '{value}'")
        
        # Test just the selected_events field
        selected_events_value = request.POST.get('selected_events', '')
        logger.info(f"selected_events raw value: '{selected_events_value}'")
        
        # Create a minimal form with just required fields for testing
        test_data = {
            'name': request.POST.get('name', 'Test User'),
            'email': request.POST.get('email', 'test@example.com'),
            'mobile_number': request.POST.get('mobile_number', '+8801234567890'),
            'grade': request.POST.get('grade', ''),
            'roll': request.POST.get('roll', '123'),
            'selected_events': selected_events_value,
        }
        
        form = StudentRegistrationForm(test_data)
        
        if form.is_valid():
            logger.info("✅ Form validation PASSED")
            selected_events = form.cleaned_data['selected_events']
            logger.info(f"Cleaned selected_events: {[opt.id for opt in selected_events]}")
            return JsonResponse({
                'success': True,
                'message': 'Form validation passed',
                'event_count': len(selected_events)
            })
        else:
            logger.error("❌ Form validation FAILED")
            logger.error(f"Form errors: {dict(form.errors)}")
            
            # Check specifically if selected_events field has errors
            if 'selected_events' in form.errors:
                logger.error(f"selected_events specific errors: {form.errors['selected_events']}")
            
            return JsonResponse({
                'success': False,
                'message': 'Form validation failed',
                'errors': dict(form.errors)
            })
    
    return JsonResponse({'error': 'Only POST allowed'})