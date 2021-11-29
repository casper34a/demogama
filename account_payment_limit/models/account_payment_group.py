# -*- coding: utf-8 -*-
from odoo import api, models, fields
from odoo.exceptions import ValidationError

class AccountPaymentGroup(models.Model):
    _inherit = 'account.payment.group'

    credit_limit = fields.Monetary(string='Anticipo Disponible',
                                   compute='_compute_credit_limit',
                                   readonly=True)

    presented_invoice = fields.Boolean(string='Recibo Factura de Proveedor')

    invoice_amount = fields.Monetary(string='Presented Invoice amount')

    @api.depends('partner_id')
    def _compute_credit_limit(self):
        for record in self:
            balance = record.partner_id.credit - record.partner_id.debit
            if balance >= record.partner_id.debit_limit:
                record.credit_limit = 0.0
            else:
                record.credit_limit = record.partner_id.debit_limit - balance

    @api.constrains('unreconciled_amount')
    def _check_adjustment_advance(self):
        for payment in self:
            if payment.credit_limit < payment.unreconciled_amount - payment.invoice_amount:
                raise ValidationError(
                    'The Adjustment / Advance should not exceed the credit limit + invoice amount (if presented)')

    def post(self):
        for payment in self:
            if payment.credit_limit < payment.payments_amount - payment.invoice_amount:
                raise ValidationError(
                    'The Payments Amount should not exceed the credit limit + invoice amount (if presented)')
        super(AccountPaymentGroup, self).post()