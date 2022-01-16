import pytest

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from oppia.test import OppiaTransactionTestCase

from profile.models import CustomField, UserProfileCustomField, UserProfile

from tests.defaults import UNAUTHORISED_TEMPLATE


class UserUploadActivityViewTest(OppiaTransactionTestCase):
    fixtures = ['tests/test_user.json',
                'tests/test_oppia.json',
                'tests/test_quiz.json',
                'tests/test_permissions.json',
                'tests/test_course_permissions.json',
                'tests/test_customfields.json']

    fixture_root = './oppia/fixtures/reference_files/upload_users/'
    file_valid = fixture_root + 'file-valid.csv'
    file_duplicate_user = fixture_root + 'duplicate-user.csv'
    file_invalid = fixture_root + 'file-invalid.csv'
    file_valid_with_password = fixture_root + 'file-valid-with-password.csv'
    custom_fields = fixture_root + 'custom_fields.csv'
    custom_fields_updated = fixture_root + 'custom_fields_updated.csv'
    all_fields = fixture_root + 'demo_user_allfields.csv'


    template = 'profile/upload.html'
    url = reverse('profile:upload')

    def setUp(self):
        super(UserUploadActivityViewTest, self).setUp()
        self.allowed_users = [self.admin_user]
        self.disallowed_users = [self.staff_user,
                                 self.teacher_user,
                                 self.normal_user]

    def test_view_upload_permissions_get(self):

        for allowed_user in self.allowed_users:
            self.client.force_login(user=allowed_user)
            response = self.client.get(self.url)
            self.assertTemplateUsed(response, self.template)
            self.assertEqual(response.status_code, 200)

        for disallowed_user in self.disallowed_users:
            self.client.force_login(user=disallowed_user)
            response = self.client.get(self.url)
            self.assertTemplateUsed(response, UNAUTHORISED_TEMPLATE)
            self.assertEqual(response.status_code, 403)

    def test_view_upload_permissions_post(self):

        for allowed_user in self.allowed_users:
            self.client.force_login(user=allowed_user)
            response = self.client.post(self.url)
            self.assertTemplateUsed(response, self.template)
            self.assertEqual(response.status_code, 200)

        for disallowed_user in self.disallowed_users:
            self.client.force_login(user=disallowed_user)
            response = self.client.post(self.url)
            self.assertTemplateUsed(response, UNAUTHORISED_TEMPLATE)
            self.assertEqual(response.status_code, 403)

    def test_view_upload_valid_file(self):
        self.client.force_login(user=self.admin_user)

        with open(self.file_valid, 'rb') as upload_user_file:
            upload_file = SimpleUploadedFile(upload_user_file.name,
                                             upload_user_file.read())

        user_count_start = User.objects.all().count()

        self.client.post(self.url, {'upload_file': upload_file, 'only_update': True})

        user_count_end = User.objects.all().count()
        self.assertEqual(user_count_start+2, user_count_end)

    @pytest.mark.xfail(reason="works on local, but not on Github workflow")
    def test_view_upload_duplicate_user(self):
        self.client.force_login(user=self.admin_user)

        with open(self.file_duplicate_user,
                  'rb') as upload_user_file:
            upload_file = SimpleUploadedFile(upload_user_file.name,
                                             upload_user_file.read())

        user_count_start = User.objects.all().count()

        self.client.post(self.url, {'upload_file': upload_file, 'only_update': True})

        user_count_end = User.objects.all().count()
        self.assertEqual(user_count_start+2, user_count_end)

    def test_view_upload_invalid_file(self):
        self.client.force_login(user=self.admin_user)

        with open(self.file_invalid, 'rb') as upload_user_file:
            upload_file = SimpleUploadedFile(upload_user_file.name,
                                             upload_user_file.read())

        user_count_start = User.objects.all().count()

        self.client.post(self.url, {'upload_file': upload_file, 'only_update': True})

        user_count_end = User.objects.all().count()
        self.assertEqual(user_count_start, user_count_end)

    def test_view_upload_with_password(self):
        self.client.force_login(user=self.admin_user)

        with open(self.file_valid_with_password, 'rb') \
                as upload_user_file:
            upload_file = SimpleUploadedFile(upload_user_file.name,
                                             upload_user_file.read())

        user_count_start = User.objects.all().count()

        self.client.post(self.url, {'upload_file': upload_file, 'only_update': True})

        user_count_end = User.objects.all().count()
        self.assertEqual(user_count_start+2, user_count_end)

        # check can login with new password
        self.client.logout()
        self.client.login(username='user100', password='password100')
        response = self.client.get(reverse('oppia:index'))
        self.assertTemplateUsed(response, 'oppia/home.html')

    def test_custom_fields(self):
        self.client.force_login(user=self.admin_user)
        with open(self.custom_fields, 'rb') as upload_user_file:
            upload_file = SimpleUploadedFile(upload_user_file.name,
                                             upload_user_file.read())

        user_count_start = User.objects.all().count()

        self.client.post(self.url, {'upload_file': upload_file, 'only_update': True})

        user_count_end = User.objects.all().count()
        self.assertEqual(user_count_start+2, user_count_end)

        # check the user data
        country_cf = CustomField.objects.get(id='country')
        age_cf = CustomField.objects.get(id='age')
        terms_cf = CustomField.objects.get(id='agree_to_terms')

        user100 = User.objects.get(username='user100')
        self.assertEqual(user100.userprofile.phone_number, "+0123456789")
        upcf = UserProfileCustomField.objects.get(key_name=country_cf,
                                                  user=user100)
        self.assertEqual(upcf.get_value(), "Sweden")

        upcf = UserProfileCustomField.objects.get(key_name=age_cf,
                                                  user=user100)
        self.assertEqual(upcf.get_value(), 24)

        upcf = UserProfileCustomField.objects.get(key_name=terms_cf,
                                                  user=user100)
        self.assertTrue(upcf.get_value())

        user101 = User.objects.get(username='user101')
        self.assertEqual(user101.userprofile.phone_number, "+987654321")
        upcf = UserProfileCustomField.objects.get(key_name=country_cf,
                                                  user=user101)
        self.assertEqual(upcf.get_value(), "Iceland")
        upcf = UserProfileCustomField.objects.get(key_name=age_cf,
                                                  user=user101)
        self.assertEqual(upcf.get_value(), 30)

        upcf = UserProfileCustomField.objects.get(key_name=terms_cf,
                                                  user=user101)
        self.assertFalse(upcf.get_value())


    def test_custom_fields_not_updated(self):
        self.client.force_login(user=self.admin_user)
        with open(self.custom_fields, 'rb') as upload_user_file:
            upload_file = SimpleUploadedFile(upload_user_file.name,
                                             upload_user_file.read())

        self.client.post(self.url, {'upload_file': upload_file})

        user_count_start = User.objects.all().count()
        # now upload the updated file
        with open(self.custom_fields_updated, 'rb') as upload_user_file:
            upload_file = SimpleUploadedFile(upload_user_file.name,
                                             upload_user_file.read())

        self.client.post(self.url, {'upload_file': upload_file, 'only_update': True})
        user_count_end = User.objects.all().count()
        self.assertEqual(user_count_start+1, user_count_end)

        # check the user data
        cf = CustomField.objects.get(id='country')

        user100 = User.objects.get(username='user100')
        self.assertEqual(user100.userprofile.phone_number, "+0123456789")
        upcf = UserProfileCustomField.objects.get(key_name=cf, user=user100)
        self.assertEqual(upcf.get_value(), "Sweden")

        user102 = User.objects.get(username='user102')
        self.assertEqual(user102.userprofile.phone_number, "+2222222")
        upcf = UserProfileCustomField.objects.get(key_name=cf, user=user102)
        self.assertEqual(upcf.get_value(), "Russia")


    def test_existing_user_nonempty_fields_dont_update(self):
        self.client.force_login(user=self.admin_user)
        with open(self.all_fields, 'rb') as upload_user_file:
            upload_file = SimpleUploadedFile(upload_user_file.name,
                                             upload_user_file.read())

        user = User.objects.get(username='demo')
        user.first_name = 'firstname'
        user.last_name = 'lastname'
        user.save()

        profile = UserProfile.objects.get(user=user)
        profile.phone_number = '000000000'
        profile.save()

        # Remove any existing custom field
        UserProfileCustomField.objects.filter(user=user).delete()

        UserProfileCustomField.objects.create(user=user, key_name=CustomField.objects.get(id='country'), value_str='Spain')
        UserProfileCustomField.objects.create(user=user, key_name=CustomField.objects.get(id='agree_to_terms'), value_bool=False)
        UserProfileCustomField.objects.create(user=user, key_name=CustomField.objects.get(id='age'), value_int=30)

        self.client.post(self.url, {'upload_file': upload_file, 'only_update': True})

        user = User.objects.get(username='demo')
        profile = UserProfile.objects.get(user=user)

        self.assertEqual(user.first_name, 'firstname')
        self.assertEqual(user.last_name, 'lastname')
        self.assertEqual(profile.phone_number, '000000000')
        self.assertEqual(UserProfileCustomField.get_user_value(user, 'country'), 'Spain')
        self.assertEqual(UserProfileCustomField.get_user_value(user, 'agree_to_terms'), False)
        self.assertEqual(UserProfileCustomField.get_user_value(user, 'age'), 30)


    def test_existing_user_empty_fields_dont_update(self):
        self.client.force_login(user=self.admin_user)
        with open(self.all_fields, 'rb') as upload_user_file:
            upload_file = SimpleUploadedFile(upload_user_file.name,
                                             upload_user_file.read())

        user = User.objects.get(username='demo')
        user.first_name = ''
        user.last_name = ''
        user.save()

        # Remove any existing field
        UserProfileCustomField.objects.filter(user=user).delete()
        UserProfile.objects.get(user=user).delete()

        self.client.post(self.url, {'upload_file': upload_file, 'only_update': True})

        user = User.objects.get(username='demo')
        profile = UserProfile.objects.get(user=user)

        self.assertEqual(user.first_name, 'UpdatedName')
        self.assertEqual(user.last_name, 'UpdatedLastname')
        self.assertEqual(profile.phone_number, '555555555')
        self.assertEqual(UserProfileCustomField.get_user_value(user, 'country'), 'Portugal')
        self.assertEqual(UserProfileCustomField.get_user_value(user, 'agree_to_terms'), True)
        self.assertEqual(UserProfileCustomField.get_user_value(user, 'age'), 99)


    def test_existing_user_nonempty_fields_override(self):
        self.client.force_login(user=self.admin_user)
        with open(self.all_fields, 'rb') as upload_user_file:
            upload_file = SimpleUploadedFile(upload_user_file.name,
                                             upload_user_file.read())

        user = User.objects.get(username='demo')
        # Remove any existing field
        UserProfileCustomField.objects.filter(user=user).delete()

        UserProfileCustomField.objects.create(user=user, key_name=CustomField.objects.get(id='country'), value_str='Spain')
        UserProfileCustomField.objects.create(user=user, key_name=CustomField.objects.get(id='agree_to_terms'), value_bool=False)
        UserProfileCustomField.objects.create(user=user, key_name=CustomField.objects.get(id='age'), value_int=30)

        self.client.post(self.url, {'upload_file': upload_file, 'only_update': False})

        user = User.objects.get(username='demo')
        profile = UserProfile.objects.get(user=user)

        self.assertEqual(user.first_name, 'UpdatedName')
        self.assertEqual(user.last_name, 'UpdatedLastname')
        self.assertEqual(profile.phone_number, '555555555')
        self.assertEqual(UserProfileCustomField.get_user_value(user, 'country'), 'Portugal')
        self.assertEqual(UserProfileCustomField.get_user_value(user, 'agree_to_terms'), True)
        self.assertEqual(UserProfileCustomField.get_user_value(user, 'age'), 99)


    def test_existing_user_empty_fields_override(self):
        self.client.force_login(user=self.admin_user)
        with open(self.all_fields, 'rb') as upload_user_file:
            upload_file = SimpleUploadedFile(upload_user_file.name,
                                             upload_user_file.read())

        user = User.objects.get(username='demo')
        # Remove any existing field
        UserProfileCustomField.objects.filter(user=user).delete()

        self.client.post(self.url, {'upload_file': upload_file, 'only_update': False})

        user = User.objects.get(username='demo')
        profile = UserProfile.objects.get(user=user)

        self.assertEqual(user.first_name, 'UpdatedName')
        self.assertEqual(user.last_name, 'UpdatedLastname')
        self.assertEqual(profile.phone_number, '555555555')
        self.assertEqual(UserProfileCustomField.get_user_value(user, 'country'), 'Portugal')
        self.assertEqual(UserProfileCustomField.get_user_value(user, 'agree_to_terms'), True)
        self.assertEqual(UserProfileCustomField.get_user_value(user, 'age'), 99)



