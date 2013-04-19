import unittest
from AnyTree.anytree import anytree


class TestResolvingTree(unittest.TestCase):

    """ Tests """

    def setUp(self):
        super(TestResolvingTree, self).setUp()

    def test_get_ordre_import(self):

        res_country = anytree.get_ordre_importation('admin', 'admin', 'ecox_db', 'res.country',
                                                    None, None)
        res_account_account = anytree.get_ordre_importation('admin', 'admin', 'ecox_db',
                                                            'account.account', None, None)

        res_groups_exclusion = anytree.get_ordre_importation('admin', 'admin', 'ecox_db',
                                                             'res.groups',
                                                             ['ir.module.category'], None)

        res_groups = anytree.get_ordre_importation('admin', 'admin', 'ecox_db', 'res.groups', None,
                                                  None)

        self.assertEquals(res_country, ['res.country'])

        self.assertEquals(res_account_account, ['account.account.type', 'res.currency',
                                                'res.country.state', 'res.country',
                                                'report.stylesheets', 'account.payment.term',
                                                'account.fiscal.position', 'res.partner.title',
                                                'product.pricelist', 'stock.journal',
                                                'res.partner.address', 'stock.location',
                                                'stock.warehouse', 'account.analytic.account',
                                                'sale.shop', 'shop.term', 'ir.actions.actions',
                                                'res.users', 'res.partner', 'res.company',
                                                'account.account'])

        self.assertEquals(res_groups_exclusion, ['res.groups'])

        self.assertEquals(res_groups, ['ir.module.category', 'res.groups'])
