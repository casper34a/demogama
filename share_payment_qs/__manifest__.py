##############################################################################
#
#    Desarrollado por Quilsoft
#    2021 All Rights Reserved.
#
##############################################################################

{
    'name': 'Share payment',
    'version': '13.0.1.0.15',
    'category': 'Account',
    'summary': 'Share payment debt',
    'author': "Quilsoft",
    'website': 'http://github.com/quilsoft/repo-atm',
    'license': 'AGPL-3',
    'depends': [
        'account_payment_group'
    ],
    'data': [
        'views/account_payment_view.xml'
    ],
    'installable': True,
}
