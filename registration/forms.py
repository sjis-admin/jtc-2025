# registration/forms.py
from django import forms
from django.core.exceptions import ValidationError
from .models import Student, Event, School, Team, TeamMember

class TeamMemberForm(forms.Form):
    name = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent',
            'placeholder': 'Enter team member name'
        })
    )

class BaseTeamMemberFormSet(forms.BaseFormSet):
    def clean(self):
        if any(self.errors):
            return

        names = []
        for form in self.forms:
            if form.cleaned_data:
                name = form.cleaned_data['name']
                if name in names:
                    raise ValidationError("Team member names must be unique.")
                names.append(name)

class StudentRegistrationForm(forms.ModelForm):
    events = forms.ModelMultipleChoiceField(
        queryset=Event.objects.filter(is_active=True),
        widget=forms.CheckboxSelectMultiple(attrs={
            'class': 'event-checkbox',
            'hx-trigger': 'change',
            'hx-post': '/calculate-total/',
            'hx-target': '#total-amount',
            'hx-swap': 'innerHTML'
        }),
        required=True
    )
    school_college = forms.ModelChoiceField(
        queryset=School.objects.all(),
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent',
        }),
        required=False,
        empty_label="Select your school/college"
    )
    other_school = forms.CharField(
        max_length=300,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent',
            'placeholder': 'Enter your school/college name if not in the list'
        }),
        required=False
    )

    class Meta:
        model = Student
        fields = [
            'name', 'school_college', 'other_school', 'grade', 'section', 'roll',
            'email', 'mobile_number', 'events'
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent',
                'placeholder': 'Enter your full name'
            }),
            'grade': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent',
                'hx-get': '/get-group/',
                'hx-target': '#group-display',
                'hx-swap': 'innerHTML'
            }),
            'section': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent',
                'placeholder': 'Only if from SJIS'
            }),
            'roll': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent',
                'placeholder': 'Your roll number/ID'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent',
                'placeholder': 'your.email@example.com'
            }),
            'mobile_number': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent',
                'placeholder': '+8801XXXXXXXXX'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['school_college'].choices = list(self.fields['school_college'].choices) + [('', 'Other')]

    def clean(self):
        cleaned_data = super().clean()
        school_college = cleaned_data.get('school_college')
        other_school = cleaned_data.get('other_school')
        roll = cleaned_data.get('roll')

        if not school_college and not other_school:
            raise ValidationError("Please select a school/college or enter a new one.")

        if school_college and other_school:
            raise ValidationError("Please either select a school/college or enter a new one, not both.")

        if roll:
            if other_school:
                school_name = other_school
                if School.objects.filter(name=school_name).exists():
                    school = School.objects.get(name=school_name)
                    if Student.objects.filter(school_college=school, roll=roll).exists():
                        raise ValidationError("A student with this roll number from this school/college is already registered.")
            elif school_college:
                if Student.objects.filter(school_college=school_college, roll=roll).exists():
                    raise ValidationError("A student with this roll number from this school/college is already registered.")

        events = cleaned_data.get('events')
        if not events:
            raise ValidationError("Please select at least one event.")

        return cleaned_data

class BulkSchoolForm(forms.Form):
    school_names = forms.CharField(
        widget=forms.Textarea(
            attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent',
                'placeholder': 'Enter school names, one per line'
            }
        ),
        help_text='Enter one school name per line. Duplicate names will be ignored.'
    )
