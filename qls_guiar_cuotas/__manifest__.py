# -*- coding: utf-8 -*-
{
    'name': "Guiar plan de pagos",

    'summary': u"""Quilsoft Guiar plan de pagos""",

    'description': u"""
        Gestion de plan de pagos con ordenes .
    """,

    'author': "Quilsoft",
    'website': "https://www.quilsoft.com",
    'category': 'Specific Industry Applications',
    'version': '13.1.0.1',
    'depends': ['base', 'sale','account_interests','account_interests_journal'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/data.xml',

        'views/inherit_views/sale_order_view.xml',
        'views/inherit_views/sale_advance_payment.xml',
        'views/inherit_views/invoice_move_view.xml',
        'views/inherit_views/res_config_account.xml',
        'views/qls_indice_view.xml',
        'views/res_company_interest.xml',

        'ir_cron.xml'
    ],
    'qweb': [],
    'installable': True,
    'auto_install': False

}
