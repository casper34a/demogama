# -*- coding: utf-8 -*-
{
    'name': 'Constructora Guiar SRL: Payment Vendor Control',

    'summary': 'Payment Vendor Control, issue payment with the constraint of invoice amount and credit line',

    'description': """
    Task ID: 2562681
        - Rebuild the studio fields
        - Create the constraints on the Adjustment/Advance fields
        - Calculate the left credits according to invoices and credits
    """,

    'author': 'Odoo',
    'website': 'https://www.odoo.com/',

    'category': 'Custom Development',
    'version': '1.0',
    'license': 'OEEL-1',

    # any module necessary for this one to work correctly
    'depends': ['account_accountant',
                'contacts',
                'l10n_ar_ux',
                'l10n_ar_edi',
                'account_payment_group',
                'account_withholding_automatic',
                ],

    # always loaded
    'data': [
        'views/account_payment_group_view_inherit.xml'
    ],
}
