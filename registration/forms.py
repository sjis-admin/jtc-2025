# registration/forms.py - FIXED VERSION
from django import forms
from django.core.exceptions import ValidationError
from .models import Student, School, Grade, EventOption
import logging

logger = logging.getLogger(__name__)

class StudentRegistrationForm(forms.ModelForm):
    # Add hidden field for selected events - FIXED: Make it not required initially
    selected_events = forms.CharField(widget=forms.HiddenInput(), required=False)
    
    # Add other school field
    other_school = forms.CharField(
        max_length=300,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent',
            'placeholder': 'Enter your school/college name'
        })
    )

    class Meta:
        model = Student
        fields = ['name', 'email', 'mobile_number', 'school_college', 'other_school', 
                 'grade', 'section', 'roll', 'selected_events']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent',
                'placeholder': 'Enter your full name'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent',
                'placeholder': 'Enter your email address'
            }),
            'mobile_number': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent',
                'placeholder': '01XXXXXXXXX'
            }),
            'school_college': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent'
            }),
            'grade': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent',
                'id': 'id_grade'
            }),
            'section': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent',
                'placeholder': 'e.g., A, B, C'
            }),
            'roll': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent',
                'placeholder': 'Enter your roll number/ID'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Setup school choices
        schools = School.objects.all().order_by('name')
        school_choices = [('', 'Other (specify below)')]
        school_choices.extend([(school.id, school.name) for school in schools])
        self.fields['school_college'].choices = school_choices
        
        # Setup grade choices
        grades = Grade.objects.all().order_by('order')
        grade_choices = [('', 'Select your grade')]
        grade_choices.extend([(grade.id, grade.name) for grade in grades])
        self.fields['grade'].choices = grade_choices

    def clean_selected_events(self):
        """Clean and validate selected events - ULTRA ROBUST VERSION"""
        selected_events = self.cleaned_data.get('selected_events', '')
        
        # Debug logging
        logger.info(f"clean_selected_events called with: '{selected_events}' (type: {type(selected_events)})")
        
        # Handle empty values
        if not selected_events or selected_events.strip() == '':
            logger.error("Selected events is empty or None")
            raise ValidationError("Please select at least one event.")
        
        try:
            # Handle various input formats
            event_option_ids = []
            
            # Remove any quotes from the string
            cleaned_string = selected_events.replace('"', '').replace("'", "")
            
            # Handle array format like [9] or regular format like 9,10
            if cleaned_string.startswith('[') and cleaned_string.endswith(']'):
                cleaned_string = cleaned_string.strip('[]')
            
            # Split by comma and remove empty strings
            id_strings = [id_str.strip() for id_str in cleaned_string.split(',') if id_str.strip()]
            
            # Convert to integers
            for id_str in id_strings:
                if id_str.isdigit():
                    event_option_ids.append(int(id_str))
                else:
                    logger.warning(f"Non-digit value found in selected_events: {id_str}")
            
            logger.info(f"Parsed event option IDs: {event_option_ids}")
            
            if not event_option_ids:
                logger.error("No valid event option IDs found after parsing")
                raise ValidationError("Please select at least one event.")
            
            # Validate that all event options exist and are active
            event_options = EventOption.objects.filter(
                id__in=event_option_ids, 
                event__is_active=True
            )
            
            found_ids = list(event_options.values_list('id', flat=True))
            logger.info(f"Found valid event options with IDs: {found_ids}")
            
            if len(event_options) != len(event_option_ids):
                missing_ids = set(event_option_ids) - set(found_ids)
                logger.error(f"Some event options not found or inactive. Missing IDs: {missing_ids}")
                raise ValidationError("One or more selected events are invalid or inactive.")
            
            # Additional validation: Check if student can register for these events based on grade
            grade = self.cleaned_data.get('grade')
            if grade:
                invalid_events = []
                for event_option in event_options:
                    if not event_option.event.target_grades.filter(id=grade.id).exists():
                        invalid_events.append(event_option.event.name)
                
                if invalid_events:
                    logger.error(f"Events not available for grade {grade.name}: {invalid_events}")
                    raise ValidationError(f"The following events are not available for {grade.name}: {', '.join(invalid_events)}")
            
            logger.info(f"Validation successful for {len(event_options)} event options")
            return event_options
            
        except ValueError as e:
            logger.error(f"ValueError parsing selected_events '{selected_events}': {e}")
            raise ValidationError("Invalid event selection format.")
        except Exception as e:
            logger.error(f"Unexpected error in clean_selected_events: {e}")
            raise ValidationError("An error occurred validating your event selection.")

    def clean_other_school(self):
        """Clean other school field"""
        school_college = self.cleaned_data.get('school_college')
        other_school = self.cleaned_data.get('other_school', '').strip()
        
        if not school_college and not other_school:
            raise ValidationError("Please specify your school/college name.")
        
        return other_school

    def clean(self):
        """Additional form validation with enhanced debugging"""
        cleaned_data = super().clean()
        
        logger.info("=== FORM CLEAN METHOD DEBUG ===")
        logger.info(f"cleaned_data keys: {list(cleaned_data.keys())}")
        logger.info(f"selected_events in cleaned_data: {cleaned_data.get('selected_events', 'NOT_FOUND')}")
        
        # Validate school selection
        school_college = cleaned_data.get('school_college')
        other_school = cleaned_data.get('other_school', '').strip()
        
        if not school_college and not other_school:
            logger.error("Neither school_college nor other_school provided")
            raise ValidationError("Please select or specify your school/college.")
        
        # Validate grade selection
        grade = cleaned_data.get('grade')
        if not grade:
            logger.error("No grade selected")
            raise ValidationError("Please select your grade.")
        
        logger.info("=== FORM CLEAN METHOD END ===")
        
        return cleaned_data

class BulkSchoolForm(forms.Form):
    """Form for bulk adding schools"""
    schools = forms.CharField(
        widget=forms.Textarea(attrs={
            'rows': 10,
            'cols': 50,
            'placeholder': 'Enter school names, one per line:\n\nABC School\nXYZ College\nPQR Institute'
        }),
        help_text='Enter one school name per line. Duplicate schools will be ignored.'
    )

    def clean_schools(self):
        """Clean and validate school names"""
        schools_text = self.cleaned_data['schools']
        school_names = []
        
        if not schools_text.strip():
            raise ValidationError('Please enter at least one school name.')
        
        # Split by lines and clean each name
        lines = schools_text.split('\n')
        for line in lines:
            school_name = line.strip()
            if school_name and len(school_name) <= 300:  # Respect model max_length
                school_names.append(school_name)
            elif school_name and len(school_name) > 300:
                raise ValidationError(f'School name "{school_name[:50]}..." is too long (max 300 characters).')
        
        if not school_names:
            raise ValidationError('No valid school names found. Please check your input.')
        
        # Remove duplicates while preserving order
        unique_schools = []
        seen = set()
        for name in school_names:
            if name.lower() not in seen:
                unique_schools.append(name)
                seen.add(name.lower())
        
        return unique_schools

class AdminStudentUpdateForm(forms.ModelForm):
    """Form for admin to update student information"""
    class Meta:
        model = Student
        fields = ['name', 'email', 'mobile_number', 'school_college', 'grade', 'section', 'roll', 'is_paid', 'payment_verified']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'mobile_number': forms.TextInput(attrs={'class': 'form-control'}),
            'school_college': forms.Select(attrs={'class': 'form-control'}),
            'grade': forms.Select(attrs={'class': 'form-control'}),
            'section': forms.TextInput(attrs={'class': 'form-control'}),
            'roll': forms.TextInput(attrs={'class': 'form-control'}),
        }

class PaymentVerificationForm(forms.Form):
    """Form for manual payment verification"""
    verify = forms.BooleanField(
        required=False,
        label='Mark as Verified',
        help_text='Check this box to verify the payment manually.'
    )
    notes = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
        required=False,
        label='Verification Notes',
        help_text='Optional notes about the verification.'
    )

class BulkActionForm(forms.Form):
    """Form for bulk actions on students"""
    ACTION_CHOICES = [
        ('', 'Select Action'),
        ('verify_payment', 'Verify Payment'),
        ('mark_paid', 'Mark as Paid'),
        ('send_email', 'Send Confirmation Email'),
        ('export_csv', 'Export to CSV'),
        ('delete', 'Delete (Soft)'),
    ]
    
    action = forms.ChoiceField(
        choices=ACTION_CHOICES,
        required=True,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    student_ids = forms.CharField(
        widget=forms.HiddenInput(),
        required=True
    )

class EmailForm(forms.Form):
    """Form for sending emails to students"""
    subject = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        help_text='Email subject line'
    )
    message = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 10, 'class': 'form-control'}),
        help_text='Email message content'
    )
    include_receipt = forms.BooleanField(
        required=False,
        label='Include Receipt',
        help_text='Attach the registration receipt to the email'
    )