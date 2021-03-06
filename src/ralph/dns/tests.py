# -*- coding: utf-8 -*-
from unittest.mock import patch

from django.db import transaction
from django.test import override_settings, TestCase, TransactionTestCase
from django.utils.translation import ugettext_lazy as _

from ralph.assets.tests.factories import (
    ConfigurationClassFactory,
    EthernetFactory
)
from ralph.data_center.models import BaseObjectCluster, DataCenterAsset
from ralph.dns.dnsaas import DNSaaS
from ralph.dns.forms import DNSRecordForm, RecordType
from ralph.dns.publishers import _get_txt_data_to_publish_to_dnsaas
from ralph.dns.views import (
    add_errors,
    DNSaaSIntegrationNotEnabledError,
    DNSView
)
from ralph.networks.tests.factories import IPAddressFactory
from ralph.virtual.models import VirtualServer
from ralph.virtual.tests.factories import VirtualServerFactory


class TestGetDnsRecords(TestCase):

    def setUp(self):
        self.dnsaas = DNSaaS()

    @patch.object(DNSaaS, 'get_api_result')
    def test_return_empty_when_api_returns_empty(self, mocked):
        mocked.return_value = []
        found_dns = self.dnsaas.get_dns_records(['192.168.0.1'])
        self.assertEqual(found_dns, [])

    def test_return_empty_when_no_ipaddress(self):
        found_dns = self.dnsaas.get_dns_records([])
        self.assertEqual(found_dns, [])

    @patch.object(DNSaaS, 'get_api_result')
    def test_return_dns_records_when_api_returns_records(self, mocked):
        data = {
            'content': '127.0.0.3',
            'name': '1.test.pl',
            'type': 'A',
            'id': 1
        }
        mocked.return_value = [data]
        found_dns = self.dnsaas.get_dns_records(['192.168.0.1'])
        self.assertEqual(len(found_dns), 1)
        self.assertEqual(found_dns[0]['content'], data['content'])
        self.assertEqual(found_dns[0]['name'], data['name'])
        self.assertEqual(found_dns[0]['type'], RecordType.a)

    @override_settings(DNSAAS_URL='http://dnsaas.com/')
    def test_build_url(self):
        self.assertEqual(
            self.dnsaas.build_url('domains'),
            'http://dnsaas.com/api/v2/domains/'
        )

    @override_settings(DNSAAS_URL='http://dnsaas.com/')
    def test_build_url_with_version(self):
        self.assertEqual(
            self.dnsaas.build_url('domains', version='v1'),
            'http://dnsaas.com/api/v1/domains/'
        )

    @override_settings(DNSAAS_URL='http://dnsaas.com/')
    def test_build_url_with_id(self):
        self.assertEqual(
            self.dnsaas.build_url('domains', id=1),
            'http://dnsaas.com/api/v2/domains/1/'
        )

    @override_settings(DNSAAS_URL='http://dnsaas.com/')
    def test_build_url_with_get_params(self):
        self.assertEqual(
            self.dnsaas.build_url('domains', get_params=[('name', 'ralph')]),
            'http://dnsaas.com/api/v2/domains/?name=ralph'
        )

    @override_settings(DNSAAS_URL='http://dnsaas.com/')
    def test_build_url_with_id_and_get_params(self):
        self.assertEqual(
            self.dnsaas.build_url(
                'domains', id=1, get_params=[('name', 'ralph')]
            ),
            'http://dnsaas.com/api/v2/domains/1/?name=ralph'
        )


class TestDNSView(TestCase):
    @override_settings(ENABLE_DNSAAS_INTEGRATION=False)
    def test_dnsaasintegration_disabled(self):
        with self.assertRaises(DNSaaSIntegrationNotEnabledError):
            DNSView()

    @override_settings(ENABLE_DNSAAS_INTEGRATION=True)
    def test_dnsaasintegration_enabled(self):
        # should not raise exception
        DNSView()


class TestGetTXTDataToPublishToDNSaaS(TestCase):

    @classmethod
    def setUpClass(cls):
        from ralph.data_center.tests.factories import (
            ClusterFactory,
            DataCenterAssetFactory,
            RackFactory,
        )
        super().setUpClass()
        cls.dc_asset = DataCenterAssetFactory(
            hostname='ralph0.allegro.pl',
            service_env__service__name='service',
            service_env__environment__name='test',
            model__name='DL360',
            model__manufacturer__name='Asus',
            model__category__name='ATS',
            rack=RackFactory(
                name='Rack #100',
                server_room__name='Server Room A',
                server_room__data_center__name='DC1',
            ),
            position=1,
            slot_no='1',
            configuration_path__class_name='www',
            configuration_path__module__name='ralph',
        )
        cls.dc_ip = IPAddressFactory(
            base_object=cls.dc_asset,
            ethernet=EthernetFactory(base_object=cls.dc_asset),
        )
        IPAddressFactory(
            base_object=cls.dc_asset,
            ethernet=EthernetFactory(base_object=cls.dc_asset),
            is_management=True,
        )
        cls.virtual_server = VirtualServerFactory(
            hostname='s000.local',
            configuration_path=ConfigurationClassFactory(
                class_name='worker',
                module__name='auth'
            ),
            service_env__service__name='service',
            service_env__environment__name='prod',
            parent=DataCenterAssetFactory(
                hostname='parent',
                model__name='DL380p',
                model__manufacturer__name='Brother',
                model__category__name='Database Machine',
                rack=RackFactory(
                    name='Rack #101',
                    server_room__name='Server Room B',
                    server_room__data_center__name='DC2',
                ),
                position=1,
                slot_no='1',
            ),
        )
        # refresh virtual server to get parent as BaseObject, not
        # DataCenterAsset
        cls.vs_ip = IPAddressFactory(
            base_object=cls.virtual_server,
            ethernet=EthernetFactory(base_object=cls.virtual_server),
        )
        cls.virtual_server = VirtualServer.objects.get(
            pk=cls.virtual_server.id
        )

        cluster = ClusterFactory(
            hostname='',
            type__name='Application',
            configuration_path__class_name='www',
            configuration_path__module__name='ralph',
            service_env__service__name='service',
            service_env__environment__name='preprod',
        )
        cls.boc_1 = BaseObjectCluster.objects.create(
            cluster=cluster,
            base_object=DataCenterAssetFactory(
                rack=RackFactory(), position=1,
            )
        )
        cls.boc_2 = BaseObjectCluster.objects.create(
            cluster=cluster,
            base_object=DataCenterAssetFactory(
                rack=RackFactory(
                    server_room__data_center__name='DC2',
                    server_room__name='Server Room B',
                    name='Rack #101',
                ),
                position=1,
            ),
            is_master=True
        )

        cls.cluster = ClusterFactory._meta.model.objects.get(pk=cluster)
        cls.cluster_ip = IPAddressFactory(
            base_object=cls.cluster,
            ethernet=EthernetFactory(base_object=cls.cluster),
        )

    def test_dc_asset_gets_data_ok(self):
        data = _get_txt_data_to_publish_to_dnsaas(self.dc_asset)
        self.assertEqual(data, [{
            'content': 'www',
            'ips': [self.dc_ip.address],
            'owner': '',
            'target_owner': 'ralph',
            'purpose': 'VENTURE'
        }, {
            'content': 'ralph',
            'ips': [self.dc_ip.address],
            'owner': '',
            'target_owner': 'ralph',
            'purpose': 'ROLE',
        }, {
            'content': 'ralph/www',
            'ips': [self.dc_ip.address],
            'owner': '',
            'target_owner': 'ralph',
            'purpose': 'CONFIGURATION_PATH',
        }, {
            'content': 'service - test',
            'ips': [self.dc_ip.address],
            'owner': '',
            'target_owner': 'ralph',
            'purpose': 'SERVICE_ENV',
        }, {
            'content': '[ATS] Asus DL360',
            'ips': [self.dc_ip.address],
            'owner': '',
            'target_owner': 'ralph',
            'purpose': 'MODEL'
        }, {
            'content': 'DC1 / Server Room A / Rack #100 / 1 / 1',
            'ips': [self.dc_ip.address],
            'owner': '',
            'target_owner': 'ralph',
            'purpose': 'LOCATION'
        }])

    def test_virtual_server_gets_data_ok(self):
        data = _get_txt_data_to_publish_to_dnsaas(self.virtual_server)
        self.assertEqual(data, [{
            'content': 'worker',
            'ips': [self.vs_ip.address],
            'owner': '',
            'target_owner': 'ralph',
            'purpose': 'VENTURE'
        }, {
            'content': 'auth',
            'ips': [self.vs_ip.address],
            'owner': '',
            'target_owner': 'ralph',
            'purpose': 'ROLE'
        }, {
            'content': 'auth/worker',
            'ips': [self.vs_ip.address],
            'owner': '',
            'target_owner': 'ralph',
            'purpose': 'CONFIGURATION_PATH',
        }, {
            'content': 'service - prod',
            'ips': [self.vs_ip.address],
            'owner': '',
            'target_owner': 'ralph',
            'purpose': 'SERVICE_ENV',
        }, {
            'content': '[Database Machine] Brother DL380p',
            'ips': [self.vs_ip.address],
            'owner': '',
            'target_owner': 'ralph',
            'purpose': 'MODEL'
        }, {
            'content': 'DC2 / Server Room B / Rack #101 / 1 / 1 / parent',
            'ips': [self.vs_ip.address],
            'owner': '',
            'target_owner': 'ralph',
            'purpose': 'LOCATION'
        }])

    def test_cluster_gets_data_ok(self):
        data = _get_txt_data_to_publish_to_dnsaas(self.cluster)
        self.assertEqual(data, [{
            'content': 'www',
            'ips': [self.cluster_ip.address],
            'owner': '',
            'target_owner': 'ralph',
            'purpose': 'VENTURE'
        }, {
            'content': 'ralph',
            'ips': [self.cluster_ip.address],
            'owner': '',
            'target_owner': 'ralph',
            'purpose': 'ROLE'
        }, {
            'content': 'ralph/www',
            'ips': [self.cluster_ip.address],
            'owner': '',
            'target_owner': 'ralph',
            'purpose': 'CONFIGURATION_PATH',
        }, {
            'content': 'service - preprod',
            'ips': [self.cluster_ip.address],
            'owner': '',
            'target_owner': 'ralph',
            'purpose': 'SERVICE_ENV',
        }, {
            'content': 'Application',
            'ips': [self.cluster_ip.address],
            'owner': '',
            'target_owner': 'ralph',
            'purpose': 'MODEL'
        }, {
            'content': 'DC2 / Server Room B / Rack #101 / 1',
            'ips': [self.cluster_ip.address],
            'owner': '',
            'target_owner': 'ralph',
            'purpose': 'LOCATION'
        }])


class TestPublishAutoTXTToDNSaaS(TransactionTestCase):

    @classmethod
    def setUpClass(cls):
        from ralph.data_center.tests.factories import (
            DataCenterAssetFactory,
            RackFactory,
        )
        super().setUpClass()
        cls.dc_asset = DataCenterAssetFactory(
            hostname='ralph0.allegro.pl',
            service_env__service__name='service',
            service_env__environment__name='test',
            model__name='DL360',
            model__manufacturer__name='Asus',
            model__category__name='ATS',
            rack=RackFactory(
                name='Rack #100',
                server_room__name='Server Room A',
                server_room__data_center__name='DC1',
            ),
            position=1,
            slot_no='1',
            configuration_path__class_name='www',
            configuration_path__module__name='ralph',
        )
        cls.dc_ip = IPAddressFactory(
            base_object=cls.dc_asset,
            ethernet=EthernetFactory(base_object=cls.dc_asset),
        )
        IPAddressFactory(
            base_object=cls.dc_asset,
            ethernet=EthernetFactory(base_object=cls.dc_asset),
            is_management=True,
        )

    @override_settings(
        DNSAAS_AUTO_TXT_RECORD_TOPIC_NAME='dnsaas_auto_txt_record'
    )
    @patch('ralph.dns.publishers.publish')
    def test_publishing_auto_txt_data_when_dc_asset_updated(self, publish_mock):
        # fetch clean instance
        dc_asset = DataCenterAsset.objects.get(pk=self.dc_asset)
        with transaction.atomic():
            dc_asset.save()

        self.assertEqual(publish_mock.call_count, 1)
        publish_data = publish_mock.call_args[0][1]
        # owner could be non-deterministic, depending on order of tests
        # and it's not part of this test to check its correctness
        for data_dict in publish_data:
            data_dict.pop('owner')
        self.assertCountEqual(publish_data, [
            {
                'content': 'www',
                'ips': [self.dc_ip.address],
                'target_owner': 'ralph',
                'purpose': 'VENTURE'
            }, {
                'content': 'ralph',
                'ips': [self.dc_ip.address],
                'target_owner': 'ralph',
                'purpose': 'ROLE',
            }, {
                'content': 'ralph/www',
                'ips': [self.dc_ip.address],
                'target_owner': 'ralph',
                'purpose': 'CONFIGURATION_PATH',
            }, {
                'content': 'service - test',
                'ips': [self.dc_ip.address],
                'target_owner': 'ralph',
                'purpose': 'SERVICE_ENV',
            }, {
                'content': '[ATS] Asus DL360',
                'ips': [self.dc_ip.address],
                'target_owner': 'ralph',
                'purpose': 'MODEL'
            }, {
                'content': 'DC1 / Server Room A / Rack #100 / 1 / 1',
                'ips': [self.dc_ip.address],
                'target_owner': 'ralph',
                'purpose': 'LOCATION'
            }
        ])


class TestDNSaaS(TestCase):
    def test_user_get_info_when_dnsaas_user_has_no_perm(self):
        class RequestStub():
            status_code = 202
        request = RequestStub()
        dns = DNSaaS()

        result = dns._response2result(request)

        self.assertEqual(
            result,
            {'non_field_errors': [
                _("Your request couldn't be handled, try later.")
            ]},
        )


class TestDNSForm(TestCase):
    def test_unknown_field_goes_to_non_field_errors(self):
        errors = {'unknown_field': ['value']}
        form = DNSRecordForm({})
        add_errors(form, errors)
        self.assertIn('value', form.non_field_errors())
