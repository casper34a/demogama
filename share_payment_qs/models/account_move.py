from odoo.tools.float_utils import float_is_zero
from odoo import fields, models, api, _
from odoo.tools import date_utils, groupby as groupbyelem
from operator import attrgetter, itemgetter
from itertools import groupby
from odoo.exceptions import UserError, ValidationError, Warning


class ModelName(models.Model):
    _inherit = 'account.move.line'
    _description = 'Description'

    def auto_reconcile_lines(self, grouped_debts=False):
        # Create list of debit and list of credit move ordered by date-currency
        debit_moves = self.filtered(lambda r: r.debit != 0 or r.amount_currency > 0)
        credit_moves = self.filtered(lambda r: r.credit != 0 or r.amount_currency < 0)
        debit_moves = debit_moves.sorted(key=lambda a: (a.date_maturity or a.date, a.currency_id))
        credit_moves = credit_moves.sorted(key=lambda a: (a.date_maturity or a.date, a.currency_id))
        # Compute on which field reconciliation should be based upon:
        if self[0].account_id.currency_id and self[0].account_id.currency_id != self[0].account_id.company_id.currency_id:
            field = 'amount_residual_currency'
        else:
            field = 'amount_residual'
        #if all lines share the same currency, use amount_residual_currency to avoid currency rounding error
        if self[0].currency_id and all([x.amount_currency and x.currency_id == self[0].currency_id for x in self]):
            field = 'amount_residual_currency'
        # Reconcile lines
        ret = self._reconcile_lines(debit_moves, credit_moves, field,grouped_debts=grouped_debts)
        return ret


    def _reconcile_lines(self, debit_moves, credit_moves, field, grouped_debts = False):
        """ This function loops on the 2 recordsets given as parameter as long as it
            can find a debit and a credit to reconcile together. It returns the recordset of the
            account move lines that were not reconciled during the process.
        """
        grouped_debts = self.grouping_invoices(debit_moves.filtered(lambda d:d.move_id.quote>0))
        (debit_moves + credit_moves).read([field])
        to_create = []
        cash_basis = debit_moves and debit_moves[0].account_id.internal_type in ('receivable', 'payable') or False
        cash_basis_percentage_before_rec = {}
        dc_vals = {}
        while (debit_moves and credit_moves):
            #ADD to quilsoft
            debt_origin = debit_moves[0].move_id.invoice_origin
            debt_quote = debit_moves[0].move_id.quote
            debit_move_g = debit_moves[0]
            # Modify to quilsoft,i search if in my grouped map there is the move in position 0
            for group in grouped_debts:
                if group.get(debt_origin, False):
                    debit_move_g = group[debt_origin][debt_quote]


            credit_move     = credit_moves[0]
            total_discount_to_debt = -credit_move.amount_residual
            total_amout = sum(d.amount_residual for d in debit_move_g)
            porcentaje_to_pay = 0
            for debit_move in debit_move_g:

                if len(debit_move_g) > 1:
                    porcentaje_to_pay = -credit_move.amount_residual/total_amout if porcentaje_to_pay==0 else porcentaje_to_pay
                    if porcentaje_to_pay<1:
                        total_discount_to_debt =    debit_move.amount_residual * porcentaje_to_pay



                company_currency = debit_move.company_id.currency_id
                # We need those temporary value otherwise the computation might be wrong below
                temp_amount_residual = min(debit_move.amount_residual, total_discount_to_debt)
                temp_amount_residual_currency = min(debit_move.amount_residual_currency,
                                                    -credit_move.amount_residual_currency)
                dc_vals[(debit_move.id, credit_move.id)] = (debit_move, credit_move, temp_amount_residual_currency)
                amount_reconcile = min(debit_move[field], total_discount_to_debt)
                # Remove from recordset the one(s) that will be totally reconciled
                # For optimization purpose, the creation of the partial_reconcile are done at the end,
                # therefore during the process of reconciling several move lines, there are actually no recompute performed by the orm
                # and thus the amount_residual are not recomputed, hence we have to do it manually.
                if amount_reconcile == debit_move[field]:
                    debit_moves -= debit_move
                else:
                    debit_move.amount_residual -= temp_amount_residual
                    debit_move.amount_residual_currency -= temp_amount_residual_currency
                if amount_reconcile == -credit_move[field]:
                    credit_moves -= credit_move
                else:
                    credit_moves[0].amount_residual += temp_amount_residual
                    credit_moves[0].amount_residual_currency += temp_amount_residual_currency
                # Check for the currency and amount_currency we can set
                currency = False
                amount_reconcile_currency = 0
                if field == 'amount_residual_currency':
                    currency = credit_move.currency_id.id
                    amount_reconcile_currency = temp_amount_residual_currency
                    amount_reconcile = temp_amount_residual
                elif bool(debit_move.currency_id) != bool(credit_move.currency_id):
                    # If only one of debit_move or credit_move has a secondary currency, also record the converted amount
                    # in that secondary currency in the partial reconciliation. That allows the exchange difference entry
                    # to be created, in case it is needed. It also allows to compute the amount residual in foreign currency.
                    currency = debit_move.currency_id or credit_move.currency_id
                    currency_date = debit_move.currency_id and credit_move.date or debit_move.date
                    amount_reconcile_currency = company_currency._convert(amount_reconcile, currency,
                                                                          debit_move.company_id, currency_date)
                    currency = currency.id
                if cash_basis:
                    tmp_set = debit_move | credit_move
                    cash_basis_percentage_before_rec.update(tmp_set._get_matched_percentage())
                add_to_exist = False

                 #The procces created generate more move tha i need, then i search if exist the move in "to_create" list, if that exist only add amounts
                for to_cre in to_create:
                    if to_cre['credit_move_id'] == credit_move.id and to_cre['debit_move_id']==debit_move.id:
                        to_cre['amount'] +=amount_reconcile
                        to_cre['amount_currency'] +=amount_reconcile_currency
                        add_to_exist = True

                if not add_to_exist:
                    to_create.append({
                        'debit_move_id': debit_move.id,
                        'credit_move_id': credit_move.id,
                        'amount': amount_reconcile,
                        'amount_currency': amount_reconcile_currency,
                        'currency_id': currency,
                    })

        cash_basis_subjected = []
        part_rec = self.env['account.partial.reconcile']
        for partial_rec_dict in to_create:
            debit_move, credit_move, amount_residual_currency = dc_vals[
                partial_rec_dict['debit_move_id'], partial_rec_dict['credit_move_id']]
            # /!\ NOTE: Exchange rate differences shouldn't create cash basis entries
            # i. e: we don't really receive/give money in a customer/provider fashion
            # Since those are not subjected to cash basis computation we process them first
            if not amount_residual_currency and debit_move.currency_id and credit_move.currency_id:
                part_rec.create(partial_rec_dict)
            else:
                cash_basis_subjected.append(partial_rec_dict)
        for after_rec_dict in cash_basis_subjected:
            new_rec = part_rec.create(after_rec_dict)
            # if the pair belongs to move being reverted, do not create CABA entry
            if cash_basis and not (
                    new_rec.debit_move_id.move_id == new_rec.credit_move_id.move_id.reversed_entry_id
                    or
                    new_rec.credit_move_id.move_id == new_rec.debit_move_id.move_id.reversed_entry_id
            ):
                new_rec.create_tax_cash_basis_entry(cash_basis_percentage_before_rec)
        return debit_moves + credit_moves





    def reconcile(self, writeoff_acc_id=False, writeoff_journal_id=False, grouped_debts=False):
        # Empty self can happen if the user tries to reconcile entries which are already reconciled.
        # The calling method might have filtered out reconciled lines.
        if not self:
            return

        # List unpaid invoices
        not_paid_invoices = self.mapped('move_id').filtered(
            lambda m: m.is_invoice(include_receipts=True) and m.invoice_payment_state not in ('paid', 'in_payment')
        )

        reconciled_lines = self.filtered(lambda aml: float_is_zero(aml.balance, precision_rounding=aml.move_id.company_id.currency_id.rounding) and aml.reconciled)
        (self - reconciled_lines)._check_reconcile_validity()
        #reconcile everything that can be
        remaining_moves = self.auto_reconcile_lines(grouped_debts=grouped_debts)

        writeoff_to_reconcile = self.env['account.move.line']
        #if writeoff_acc_id specified, then create write-off move with value the remaining amount from move in self
        if writeoff_acc_id and writeoff_journal_id and remaining_moves:
            all_aml_share_same_currency = all([x.currency_id == self[0].currency_id for x in self])
            writeoff_vals = {
                'account_id': writeoff_acc_id.id,
                'journal_id': writeoff_journal_id.id
            }
            if not all_aml_share_same_currency:
                writeoff_vals['amount_currency'] = False
            writeoff_to_reconcile = remaining_moves._create_writeoff([writeoff_vals])
            #add writeoff line to reconcile algorithm and finish the reconciliation
            remaining_moves = (remaining_moves + writeoff_to_reconcile).auto_reconcile_lines(grouped_debts=grouped_debts)
        # Check if reconciliation is total or needs an exchange rate entry to be created
        (self + writeoff_to_reconcile).check_full_reconcile()

        # Trigger action for paid invoices
        not_paid_invoices.filtered(
            lambda m: m.invoice_payment_state in ('paid', 'in_payment')
        ).action_invoice_paid()

        return True

    def grouping_invoices(self, deudas):
        res = []
        if deudas:
            sorted_form_origin_file =deudas.sorted(lambda move:move.move_id.invoice_origin)

            for k, groups_for_invoice in groupby(sorted_form_origin_file,lambda move: move.move_id.invoice_origin):
                aux_map = {}

                for invoice in groups_for_invoice:
                    origen  = invoice.move_id.invoice_origin
                    quote   = invoice.move_id.quote
                    if not aux_map.get(origen, False):
                        aux_map.setdefault(origen, {})
                    if not aux_map.get(quote, False):
                        aux_map[origen].setdefault(quote, [])

                    aux_map[origen][quote].append(invoice)
                self.check_quote_constrain(aux_map,origen)
                res.append(aux_map)


        return res


    def check_quote_constrain(self, groups_for_quote, origin):
        domain_lines = [('partner_id.commercial_partner_id', '=', self[0].partner_id.commercial_partner_id.id),
                  ('account_id.internal_type', '=', self[0].account_internal_type),
                  ('account_id.reconcile', '=', True),
                  ('reconciled', '=', False),
                  ('full_reconcile_id', '=', False),
                  ('company_id', '=', self[0].company_id.id),
                  ('move_id.state', '=', 'posted')]

        #I search all move that it can be cinciled
        account_move_lines = self.env['account.move.line'].search(domain_lines)

        another_moves = account_move_lines.filtered(lambda a:a.move_id.invoice_origin == origin and a.move_id.quote >0)

        for invoice in another_moves:
            if groups_for_quote[origin].get(invoice.move_id.quote, False):
                if invoice.id not in [inv.id for inv in groups_for_quote[origin][invoice.move_id.quote]]:
                    raise Warning("Atención! El comprobante %s debe estar presente en las lineas a pagar ya que se esta intentando"
                            " pagar comprobante que esta relacionado con este."%(invoice.name))



