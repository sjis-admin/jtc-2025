# registration/urls.py - Updated with new admin URLs
from django.urls import path
from . import views
from . import admin_views

urlpatterns = [
    # Public URLs
    path('', views.home, name='home'),
    path('register/', views.register, name='register'),
    path('get-group/', views.get_group, name='get_group'),
    path('calculate-total/', views.calculate_total, name='calculate_total'),
    
    # Payment URLs
    path('payment/<int:student_id>/', views.payment_gateway, name='payment_gateway'),
    path('payment/success/<int:student_id>/', views.payment_success, name='payment_success'),
    path('payment/fail/<int:student_id>/', views.payment_fail, name='payment_fail'),
    path('payment/cancel/<int:student_id>/', views.payment_cancel, name='payment_cancel'),
    path('payment/ipn/', views.payment_ipn, name='payment_ipn'),
    
    # Admin Dashboard URLs
    path('dashboard/', admin_views.dashboard, name='admin_dashboard'),
    path('dashboard/students/', admin_views.student_list, name='admin_students'),
    path('dashboard/student/<int:student_id>/', admin_views.student_detail, name='admin_student_detail'),
    path('dashboard/payments/', admin_views.payment_list, name='admin_payments'),
    path('dashboard/events/', admin_views.event_list, name='admin_events'),
    path('dashboard/logs/', admin_views.admin_logs, name='admin_logs'),
    path('dashboard/reports/', admin_views.reports, name='admin_reports'),
    path('dashboard/schools/bulk-add/', admin_views.bulk_add_schools, name='bulk_add_schools'),
    path('dashboard/reports/export/', admin_views.export_detailed_report, name='export_detailed_report'),
    path('dashboard/reports/print/', admin_views.print_detailed_report_pdf, name='print_detailed_report'),
    path('dashboard/verify-payment/<int:payment_id>/', admin_views.verify_payment, name='verify_payment'),
    path('dashboard/generate-receipt/<int:student_id>/', admin_views.generate_receipt, name='generate_receipt'),
    path('dashboard/send-email/<int:student_id>/', admin_views.send_email, name='send_email'),
    
    # New URLs for bulk actions and delete
    path('dashboard/bulk-action/', admin_views.bulk_action, name='bulk_action'),
    path('dashboard/delete-student/<int:student_id>/', admin_views.delete_student, name='delete_student'),
    path('dashboard/logout/', admin_views.logout_view, name='admin_logout'),
    path('dashboard/verify-payment/<int:payment_id>/', admin_views.verify_payment, name='admin_verify_payment'),
    path('qr-code/<str:receipt_number>/', views.generate_qr_code, name='generate_qr_code'),
    path('verify/receipt/<str:receipt_number>/', views.verify_receipt, name='verify_receipt'),
]