from odoo import fields, models, api, _
from odoo.tools import date_utils, groupby as groupbyelem
from operator import attrgetter, itemgetter
from itertools import groupby
from odoo.exceptions import UserError, ValidationError


class AccountPayment(models.Model):
    _inherit = 'account.payment.group'
    _description = 'Payment Group'

    def post(self):
        create_from_website = self._context.get('create_from_website', False)
        create_from_statement = self._context.get('create_from_statement', False)
        create_from_expense = self._context.get('create_from_expense', False)
        for rec in self:
            # TODO if we want to allow writeoff then we can disable this
            # constrain and send writeoff_journal_id and writeoff_acc_id
            if not rec.payment_ids:
                raise ValidationError(_(
                    'You can not confirm a payment group without payment '
                    'lines!'))
            # si el pago se esta posteando desde statements y hay doble
            # validacion no verificamos que haya deuda seleccionada
            if (rec.payment_subtype == 'double_validation' and
                    rec.payment_difference and (not create_from_statement and
                                                not create_from_expense)):
                raise ValidationError(_(
                    'To Pay Amount and Payment Amount must be equal!'))

            writeoff_acc_id = False
            writeoff_journal_id = False
            # if the partner of the payment is different of ht payment group we change it.
            rec.payment_ids.filtered(lambda p : p.partner_id != rec.partner_id).write(
                {'partner_id': rec.partner_id.id})
            # al crear desde website odoo crea primero el pago y lo postea
            # y no debemos re-postearlo
            if not create_from_website and not create_from_expense:
                rec.payment_ids.filtered(lambda x: x.state == 'draft').post()

            counterpart_aml = rec.payment_ids.mapped('move_line_ids').filtered(
                lambda r: not r.reconciled and r.account_id.internal_type in (
                    'payable', 'receivable'))

            # porque la cuenta podria ser no recivible y ni conciliable
            # (por ejemplo en sipreco)

            if counterpart_aml and rec.to_pay_move_line_ids:
                moves_to_reconcile = counterpart_aml + (rec.to_pay_move_line_ids)
                grouped = moves_to_reconcile.filtered(lambda move:move.move_id.type == 'out_invoice' and move.move_id.quote > 0)
                (moves_to_reconcile).reconcile(
                    writeoff_acc_id, writeoff_journal_id, grouped_debts=True if grouped else False)

            rec.state = 'posted'
        return True







