# registration/admin.py
from django.contrib import admin
from django.shortcuts import redirect
from django.utils.html import format_html
from django.urls import path, reverse
from django.http import HttpResponseRedirect
from django.contrib import messages
from django.db.models import Count
from .models import (Student, Event, Payment, AdminLog, Receipt, 
                    StudentEventRegistration, School, Countdown, 
                    HomePageAsset, SocialMediaProfile, TeamMemberProfile, PastEventImage)

@admin.register(TeamMemberProfile)
class TeamMemberProfileAdmin(admin.ModelAdmin):
    list_display = ('name', 'designation', 'member_type')

@admin.register(PastEventImage)
class PastEventImageAdmin(admin.ModelAdmin):
    list_display = ('caption',)

@admin.register(HomePageAsset)
class HomePageAssetAdmin(admin.ModelAdmin):
    list_display = ('title', 'asset_type', 'is_active', 'created_at')

@admin.register(SocialMediaProfile)
class SocialMediaProfileAdmin(admin.ModelAdmin):
    list_display = ('platform', 'url', 'is_active')

@admin.register(Countdown)
class CountdownAdmin(admin.ModelAdmin):
    list_display = ('title', 'target_date', 'is_active')

@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    list_display = ['name', 'created_at']
    search_fields = ['name']
    ordering = ['name']
    change_list_template = "admin/registration/school/change_list.html"

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['bulk_add_url'] = reverse('bulk_add_schools')
        return super().changelist_view(request, extra_context=extra_context)
from .utils import log_admin_action, get_client_ip

class StudentEventRegistrationInline(admin.TabularInline):
    model = StudentEventRegistration
    extra = 0
    readonly_fields = ['registered_at']

@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = [
        'registration_id', 'name', 'school_college', 'grade', 'group', 'email', 
        'mobile_number', 'total_amount', 'payment_status', 'created_at'
    ]
    list_filter = [
        'grade', 'group', 'is_paid', 'payment_verified', 'created_at', 'school_college'
    ]
    search_fields = ['registration_id', 'name', 'email', 'mobile_number', 'roll', 'school_college']
    readonly_fields = ['registration_id', 'group', 'total_amount', 'created_at', 'updated_at']
    ordering = ['-created_at']
    date_hierarchy = 'created_at'
    
    inlines = [StudentEventRegistrationInline]
    
    fieldsets = (
        ('Personal Information', {
            'fields': ('name', 'email', 'mobile_number')
        }),
        ('Academic Information', {
            'fields': ('school_college', 'grade', 'group', 'section', 'roll')
        }),
        ('Registration Details', {
            'fields': ('registration_id', 'total_amount', 'is_paid', 'payment_verified')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['mark_as_paid', 'mark_as_unpaid', 'send_confirmation_email']
    
    def payment_status(self, obj):
        if obj.is_paid:
            color = 'green'
            status = 'Paid'
            if obj.payment_verified:
                status += ' ✓'
        else:
            color = 'red'
            status = 'Unpaid'
        return format_html('<span style="color: {};">{}</span>', color, status)
    payment_status.short_description = 'Payment Status'
    
    def mark_as_paid(self, request, queryset):
        updated = queryset.update(is_paid=True, payment_verified=True)
        
        # Log the action
        log_admin_action(
            user=request.user,
            action='UPDATE',
            model_name='Student',
            object_id=','.join([str(obj.id) for obj in queryset]),
            description=f'Marked {updated} students as paid',
            ip_address=get_client_ip(request)
        )
        
        self.message_user(request, f'{updated} students marked as paid.')
    mark_as_paid.short_description = 'Mark selected students as paid'
    
    def mark_as_unpaid(self, request, queryset):
        updated = queryset.update(is_paid=False, payment_verified=False)
        
        log_admin_action(
            user=request.user,
            action='UPDATE',
            model_name='Student',
            object_id=','.join([str(obj.id) for obj in queryset]),
            description=f'Marked {updated} students as unpaid',
            ip_address=get_client_ip(request)
        )
        
        self.message_user(request, f'{updated} students marked as unpaid.')
    mark_as_unpaid.short_description = 'Mark selected students as unpaid'
    
    def send_confirmation_email(self, request, queryset):
        from .views import send_registration_email
        count = 0
        for student in queryset:
            if student.is_paid:
                receipt = student.receipts.first()
                if receipt:
                    try:
                        send_registration_email(student, receipt)
                        count += 1
                    except Exception:
                        pass
        
        log_admin_action(
            user=request.user,
            action='EMAIL_SENT',
            model_name='Student',
            description=f'Sent confirmation emails to {count} students',
            ip_address=get_client_ip(request)
        )
        
        self.message_user(request, f'Sent confirmation emails to {count} students.')
    send_confirmation_email.short_description = 'Send confirmation email'
    
    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        
        action = 'UPDATE' if change else 'CREATE'
        log_admin_action(
            user=request.user,
            action=action,
            model_name='Student',
            object_id=str(obj.id),
            description=f'{action.lower()}d student: {obj.name}',
            ip_address=get_client_ip(request)
        )

@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ['name', 'fee', 'event_type', 'max_team_size', 'is_active', 'registration_count', 'created_at']
    list_filter = ['is_active', 'event_type', 'created_at']
    search_fields = ['name', 'description']
    ordering = ['-created_at']
    
    fieldsets = (
        (None, {
            'fields': ('name', 'description', 'fee', 'is_active')
        }),
        ('Event Media', {
            'fields': ('event_image',)
        }),
        ('Event Type', {
            'fields': ('event_type', 'max_team_size', 'max_participants'),
        }),
        ('Event Rules', {
            'fields': ('rules_type', 'rules_text', 'rules_file'),
        }),
    )

    def registration_count(self, obj):
        count = obj.student_set.count()
        return format_html('<strong>{}</strong>', count)
    registration_count.short_description = 'Registrations'
    
    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            registration_count=Count('student')
        )
    
    def save_model(self, request, obj, form, change):
        if obj.event_type == 'TEAM' and not obj.max_team_size:
            messages.error(request, "Max team size is required for team events.")
            return
        
        super().save_model(request, obj, form, change)
        
        action = 'UPDATE' if change else 'CREATE'
        log_admin_action(
            user=request.user,
            action=action,
            model_name='Event',
            object_id=str(obj.id),
            description=f'{action.lower()}d event: {obj.name}',
            ip_address=get_client_ip(request)
        )

    class Media:
        js = ('admin/js/event_admin.js',)


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = [
        'transaction_id', 'student_name', 'amount', 'payment_method', 
        'status', 'created_at'
    ]
    list_filter = ['status', 'payment_method', 'created_at']
    search_fields = ['transaction_id', 'student__name', 'student__email']
    readonly_fields = ['transaction_id', 'gateway_response', 'created_at', 'updated_at']
    ordering = ['-created_at']
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Payment Information', {
            'fields': ('student', 'transaction_id', 'amount', 'payment_method', 'status')
        }),
        ('Gateway Details', {
            'fields': ('sessionkey', 'gateway_txnid', 'gateway_response'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def student_name(self, obj):
        return obj.student.name
    student_name.short_description = 'Student'
    
    actions = ['mark_as_success', 'mark_as_failed']
    
    def mark_as_success(self, request, queryset):
        updated = 0
        for payment in queryset:
            if payment.status != 'SUCCESS':
                payment.status = 'SUCCESS'
                payment.student.is_paid = True
                payment.student.payment_verified = True
                payment.student.save()
                payment.save()
                updated += 1
        
        log_admin_action(
            user=request.user,
            action='PAYMENT_VERIFY',
            model_name='Payment',
            description=f'Marked {updated} payments as successful',
            ip_address=get_client_ip(request)
        )
        
        self.message_user(request, f'{updated} payments marked as successful.')
    mark_as_success.short_description = 'Mark selected payments as successful'
    
    def mark_as_failed(self, request, queryset):
        updated = queryset.update(status='FAILED')
        
        log_admin_action(
            user=request.user,
            action='UPDATE',
            model_name='Payment',
            description=f'Marked {updated} payments as failed',
            ip_address=get_client_ip(request)
        )
        
        self.message_user(request, f'{updated} payments marked as failed.')
    mark_as_failed.short_description = 'Mark selected payments as failed'

@admin.register(Receipt)
class ReceiptAdmin(admin.ModelAdmin):
    list_display = [
        'receipt_number', 'student_name', 'payment_amount', 
        'generated_at', 'email_sent', 'generated_by'
    ]
    list_filter = ['email_sent', 'generated_at']
    search_fields = ['receipt_number', 'student__name', 'student__email']
    readonly_fields = ['receipt_number', 'generated_at', 'email_sent_at']
    ordering = ['-generated_at']
    
    def student_name(self, obj):
        return obj.student.name
    student_name.short_description = 'Student'
    
    def payment_amount(self, obj):
        return f'৳{obj.payment.amount}'
    payment_amount.short_description = 'Amount'

@admin.register(AdminLog)
class AdminLogAdmin(admin.ModelAdmin):
    list_display = [
        'admin_user', 'action', 'model_name', 'object_id', 
        'timestamp', 'ip_address'
    ]
    list_filter = ['action', 'model_name', 'timestamp', 'admin_user']
    search_fields = ['admin_user__username', 'description', 'object_id']
    readonly_fields = ['admin_user', 'action', 'model_name', 'object_id', 'description', 'ip_address', 'timestamp']
    ordering = ['-timestamp']
    date_hierarchy = 'timestamp'
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False
    
    def has_delete_permission(self, request, obj=None):
        return False

# Customize admin site
admin.site.site_header = 'Josephite Tech Club Admin'
admin.site.site_title = 'JTC Admin'
admin.site.index_title = 'Welcome to Josephite Tech Club Administration'
