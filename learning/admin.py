from django.contrib import admin
from .models import ClassRegistration, Course, Enrollment, LiveClass, TuitionEnquiry, TuitionOffer

for m in (Course, Enrollment, LiveClass, ClassRegistration, TuitionOffer, TuitionEnquiry):
    admin.site.register(m)
