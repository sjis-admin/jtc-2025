# registration/management/commands/generate_test_data.py
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from registration.models import Student, Event, Payment, StudentEventRegistration, Receipt
from faker import Faker
import random
from decimal import Decimal

class Command(BaseCommand):
    help = 'Generate test data for development'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--students',
            type=int,
            default=50,
            help='Number of test students to create'
        )
    
    def handle(self, *args, **options):
        fake = Faker()
        num_students = options['students']
        
        # Get or create events
        events = list(Event.objects.filter(is_active=True))
        if not events:
            self.stdout.write(
                self.style.ERROR('No active events found. Please run setup_events first.')
            )
            return
        
        schools = [
            'St. Joseph Higher Secondary School',
            'Dhaka Collegiate School',
            'Holy Cross College',
            'Notre Dame College',
            'Viqarunnisa Noon School',
            'Willes Little Flower School',
            'Ideal School & College',
            'Motijheel Ideal School',
            'Shaheed Bir Uttam Lt. Anwar Girls College',
            'Adamjee Cantonment College'
        ]
        
        grades = ['3', '4', '5', '6', '7', '8', '9', '10', '11', '12']
        
        created_count = 0
        for i in range(num_students):
            # Create student
            grade = random.choice(grades)
            school = random.choice(schools)
            
            student = Student.objects.create(
                name=fake.name(),
                school_college=school,
                grade=grade,
                section=random.choice(['A', 'B', 'C', '']) if school == 'St. Joseph Higher Secondary School' else '',
                roll=str(random.randint(1, 999)).zfill(3),
                email=fake.email(),
                mobile_number=f'+8801{random.randint(100000000, 999999999)}'
            )
            
            # Add random events
            selected_events = random.sample(events, random.randint(1, min(4, len(events))))
            for event in selected_events:
                StudentEventRegistration.objects.create(
                    student=student,
                    event=event
                )
            
            # Calculate total amount
            student.calculate_total_amount()
            
            # Randomly make some payments successful
            if random.random() < 0.7:  # 70% chance of payment
                student.is_paid = True
                student.payment_verified = True
                student.save()
                
                # Create payment record
                payment = Payment.objects.create(
                    student=student,
                    transaction_id=f'TEST-{fake.uuid4()[:8].upper()}',
                    amount=student.total_amount,
                    status='SUCCESS',
                    payment_method=random.choice(['BKASH', 'ROCKET', 'NAGAD', 'CARD'])
                )
                
                # Create receipt
                Receipt.objects.create(
                    student=student,
                    payment=payment,
                    email_sent=random.choice([True, False])
                )
            
            created_count += 1
            
            if created_count % 10 == 0:
                self.stdout.write(f'Created {created_count} students...')
        
        self.stdout.write(
            self.style.SUCCESS(f'Successfully created {created_count} test students.')
        )
