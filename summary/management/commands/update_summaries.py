
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db.models import Count, Sum
from django.db.models.functions import TruncDay, \
    TruncMonth, \
    TruncYear, \
    TruncDate
from django.utils import timezone

from oppia.models import Tracker, Points, Course
from settings.models import SettingProperties
from summary.models import UserCourseSummary, \
    CourseDailyStats, \
    UserPointsSummary, \
    DailyActiveUsers, \
    DailyActiveUser


class Command(BaseCommand):
    help = 'Updates course, points and daily active users summary tables'
    MAX_TIME = 60*60*24

    def add_arguments(self, parser):

        # Optional argument to start the summary calculation from the beginning
        parser.add_argument('--fromstart',
                            action='store_true',
                            dest='fromstart',
                            help='Calculate summary tables from the beginning, \
                              not just the last ones')

    def handle(self, *args, **options):

        # check if cron already running
        prop, created = SettingProperties.objects \
            .get_or_create(key='oppia_summary_cron_lock',
                           int_value=1)
        if not created:
            self.stdout.write("Oppia summary cron is already running")
            return

        try:
            SettingProperties.objects.get(key='oppia_cron_lock')
            self.stdout.write("Oppia cron is already running")
            SettingProperties.delete_key('oppia_summary_cron_lock')
            return
        except SettingProperties.DoesNotExist:
            # do nothing
            pass

        if options['fromstart']:
            self.update_summaries(0, 0, options['fromstart'])
        else:
            # get last tracker and points PKs processed
            last_tracker_pk = SettingProperties \
                .get_property('last_tracker_pk', 0)
            last_points_pk = SettingProperties \
                .get_property('last_points_pk', 0)
            self.update_summaries(last_tracker_pk,
                                  last_points_pk)

    def update_summaries(self,
                         last_tracker_pk=0,
                         last_points_pk=0,
                         fromstart=False):

        SettingProperties.set_string('oppia_summary_cron_last_run',
                                     timezone.now())

        # get last tracker and points PKs to be processed
        # (to avoid leaving some out if new trackers arrive while processing)
        try:
            newest_tracker_pk = Tracker.objects.latest('id').id
            newest_points_pk = Points.objects.latest('id').id
        except Tracker.DoesNotExist:
            self.stdout.write("Tracker table is empty. Aborting cron...")
            SettingProperties.delete_key('oppia_summary_cron_lock')
            return
        except Points.DoesNotExist:
            newest_points_pk = last_points_pk

        print('Last tracker processed: %d\nNewest tracker: %d\n'
              % (last_tracker_pk,
                 newest_tracker_pk))
        if last_tracker_pk >= newest_tracker_pk:
            self.stdout.write('No new trackers to process. Aborting cron...')
            SettingProperties.delete_key('oppia_summary_cron_lock')
            return

        self.update_user_course_summary(last_tracker_pk,
                                        newest_tracker_pk,
                                        last_points_pk,
                                        newest_points_pk)

        self.update_course_daily_stats(last_tracker_pk,
                                       newest_tracker_pk)

        self.update_user_points_summary(last_points_pk,
                                        newest_points_pk)

        self.update_daily_active_users(last_tracker_pk,
                                       newest_tracker_pk)

        # update last tracker and points PKs with the last one processed
        SettingProperties.objects \
            .update_or_create(key='last_tracker_pk',
                              defaults={"int_value":
                                        newest_tracker_pk})
        SettingProperties.objects.update_or_create(key='last_points_pk',
                                                   defaults={"int_value":
                                                             newest_points_pk})

        SettingProperties.delete_key('oppia_summary_cron_lock')

    # Updates the UserCourseSummary model
    def update_user_course_summary(self,
                                   last_tracker_pk=0,
                                   newest_tracker_pk=0,
                                   last_points_pk=0,
                                   newest_points_pk=0):

        if last_tracker_pk == 0:
            UserCourseSummary.objects.all().delete()

        user_courses = Tracker.objects \
            .filter(pk__gt=last_tracker_pk, pk__lte=newest_tracker_pk) \
            .exclude(course__isnull=True) \
            .values('course', 'user').distinct()

        total_users = user_courses.count()
        self.stdout.write('%d different user/courses to process.'
                          % total_users)

        count = 1
        for uc_tracker in user_courses:
            self.stdout.write('processing user/course trackers... (%d/%d)'
                              % (count, total_users))
            try:
                user = User.objects.get(pk=uc_tracker['user'])
            except User.DoesNotExist:
                continue
            course = Course.objects.get(pk=uc_tracker['course'])
            user_course, created = UserCourseSummary.objects \
                .get_or_create(course=course, user=user)
            user_course.update_summary(
                last_tracker_pk=last_tracker_pk,
                last_points_pk=last_points_pk,
                newest_tracker_pk=newest_tracker_pk,
                newest_points_pk=newest_points_pk)
            count += 1

    # Updates the CourseDailyStats model
    def update_course_daily_stats(self,
                                  last_tracker_pk=0,
                                  newest_tracker_pk=0):

        if last_tracker_pk == 0:
            CourseDailyStats.objects.all().delete()

        # get different (distinct) courses/dates involved
        course_daily_type_logs = Tracker.objects \
            .filter(pk__gt=last_tracker_pk, pk__lte=newest_tracker_pk) \
            .exclude(course__isnull=True) \
            .annotate(day=TruncDay('tracker_date'),
                      month=TruncMonth('tracker_date'),
                      year=TruncYear('tracker_date')) \
            .values('course', 'day', 'month', 'year', 'type') \
            .annotate(total=Count('type')) \
            .order_by('day')

        total_logs = course_daily_type_logs.count()
        self.stdout.write('%d different courses/dates/types to process.'
                          % total_logs)
        count = 0
        for type_log in course_daily_type_logs:
            course = Course.objects.get(pk=type_log['course'])
            stats, created = CourseDailyStats.objects \
                .get_or_create(course=course,
                               day=type_log['day'],
                               type=type_log['type'])
            stats.total = (0 if last_tracker_pk == 0 else stats.total) \
                + type_log['total']
            stats.save()

            count += 1
            self.stdout.write(str(count))

        # get different (distinct) search logs involved
        search_daily_logs = Tracker.objects \
            .filter(pk__gt=last_tracker_pk,
                    pk__lte=newest_tracker_pk,
                    user__is_staff=False,
                    type='search') \
            .annotate(day=TruncDay('tracker_date'),
                      month=TruncMonth('tracker_date'),
                      year=TruncYear('tracker_date')) \
            .values('day', 'month', 'year') \
            .annotate(total=Count('id')) \
            .order_by('day')

        self.stdout.write('%d different search/dates to process.'
                          % search_daily_logs.count())
        for search_log in search_daily_logs:
            stats, created = CourseDailyStats.objects \
                .get_or_create(course=None,
                               day=search_log['day'],
                               type='search')
            stats.total = (0 if last_tracker_pk == 0 else stats.total) \
                + search_log['total']
            stats.save()

    # Updates the UserPointsSummary model
    def update_user_points_summary(self,
                                   last_points_pk=0,
                                   newest_points_pk=0):

        if last_points_pk == 0:
            UserPointsSummary.objects.all().delete()

        # get different (distinct) user/points involved
        users_points = Points.objects \
            .filter(pk__gt=last_points_pk, pk__lte=newest_points_pk) \
            .values('user').distinct()

        total_users = users_points.count()
        self.stdout.write('%d different user/points to process.' % total_users)
        for user_points in users_points:
            try:
                user = User.objects.get(pk=user_points['user'])
            except User.DoesNotExist:
                continue
            points, created = UserPointsSummary.objects \
                .get_or_create(user=user)
            points.update_points(last_points_pk=last_points_pk,
                                 newest_points_pk=newest_points_pk)

    def update_user_courses(self,
                            last_tracker_pk=0,
                            newest_tracker_pk=0,
                            last_points_pk=0,
                            newest_points_pk=0):

        user_courses = Tracker.objects \
            .filter(pk__gt=last_tracker_pk, pk__lte=newest_tracker_pk) \
            .exclude(course__isnull=True) \
            .values('course', 'user').distinct()

        total_users = user_courses.count()
        print('%d different user/courses to process.' % total_users)

        count = 1
        for uc_tracker in user_courses:
            print('processing user/course trackers... (%d/%d)' % (count,
                                                                  total_users))
            try:
                user = User.objects.get(pk=uc_tracker['user'])
            except User.DoesNotExist:
                continue
            course = Course.objects.get(pk=uc_tracker['course'])
            user_course, created = UserCourseSummary.objects \
                .get_or_create(course=course, user=user)
            user_course.update_summary(
                last_tracker_pk=last_tracker_pk,
                last_points_pk=last_points_pk,
                newest_tracker_pk=newest_tracker_pk,
                newest_points_pk=newest_points_pk)
            count += 1

    def update_daily_active_users(self,
                                  last_tracker_pk=0,
                                  newest_tracker_pk=0):

        if last_tracker_pk == 0:
            # wipe the cache table first
            DailyActiveUsers.objects.all().delete()

        courses = Course.objects.all()

        for idx, course in enumerate(courses):
            self.stdout.write(course.get_title())
            # process for tracker date
            self.update_daily_active_users_dates(
                course,
                last_tracker_pk,
                newest_tracker_pk,
                'tracker_date',
                'total_tracker_date',
                DailyActiveUser.TRACKER,
                idx,
                courses.count())

            # process for submitted date
            self.update_daily_active_users_dates(
                course,
                last_tracker_pk,
                newest_tracker_pk,
                'submitted_date',
                'total_submitted_date',
                DailyActiveUser.SUBMITTED,
                idx,
                courses.count())

    def update_daily_active_users_dates(
            self,
            course,
            last_tracker_pk,
            newest_tracker_pk,
            tracker_date_field,
            dau_total_date_field,
            dau_type,
            course_no,
            course_total):

        trackers = Tracker.objects.filter(pk__gt=last_tracker_pk,
                                          pk__lte=newest_tracker_pk,
                                          course=course) \
            .annotate(day=TruncDate(tracker_date_field)) \
            .values('day').distinct()

        # for each tracker update the DAU model
        for idx, tracker in enumerate(trackers):
            self.stdout.write('Updating DAUs for %s - %s (%s: course %d/%d DAU %d/%d)' %
                              (tracker['day'],
                               course.get_title(),
                               dau_type,
                               course_no+1,
                               course_total,
                               idx+1,
                               trackers.count()))
            total_users = Tracker.objects.annotate(
                day=TruncDate(tracker_date_field)) \
                .filter(day=tracker['day']) \
                .aggregate(number_of_users=Count('user', distinct=True))

            dau_obj, created = DailyActiveUsers.objects.update_or_create(
                day=tracker['day'],
                defaults={dau_total_date_field:
                          total_users['number_of_users']})

            users = Tracker.objects.annotate(
                day=TruncDate(tracker_date_field)) \
                .filter(day=tracker['day']).values_list('user',
                                                        flat=True).distinct()

            for user_id in users:
                self.update_daily_active_users_update(
                    tracker,
                    tracker_date_field,
                    user_id,
                    course,
                    dau_obj,
                    dau_type)

    def update_daily_active_users_update(self,
                                         tracker,
                                         tracker_date_field,
                                         user_id,
                                         course,
                                         dau_obj,
                                         dau_type):

        try:
            user_obj = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return

        time_spent = Tracker.objects.annotate(
            day=TruncDate(tracker_date_field)) \
            .filter(day=tracker['day'], user=user_obj) \
            .aggregate(time=Sum('time_taken'))

        # to avoid number out of no seconds in a day
        if time_spent['time'] > self.MAX_TIME:
            time_taken = self.MAX_TIME
        else:
            time_taken = time_spent['time']

        if time_taken != 0:
            dau, created = DailyActiveUser.objects.get_or_create(
                dau=dau_obj,
                user=user_obj,
                type=dau_type,
                course=course)
            dau.time_spent = time_taken
            dau.save()
            if created:
                self.stdout.write("added %s" % user_obj.username)
            else:
                self.stdout.write("updated %s" % user_obj.username)
