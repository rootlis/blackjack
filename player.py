import logging
from google.appengine.ext import ndb
from deck import Deck

class Player(ndb.Model):

    name = ndb.StringProperty()
    a_url = ndb.StringProperty(
            default='/static/img/kid.png')
    tokens = ndb.IntegerProperty()
    wager = ndb.IntegerProperty()
    cards_vis = ndb.KeyProperty(repeated=True)
    cards_inv = ndb.KeyProperty(repeated=True)
    cards_spl = ndb.KeyProperty(repeated=True)

    # Sync values:
    #   0 => Player has not yet taken any action
    #   1 => Player has acted, but is not standing
    #   2 => Player is standing
    #   3 => Player has surrendered
    #   4 => Player has joined game but is not playing
    sync = ndb.IntegerProperty(default=4)


    def game(self):
        
        return self.key.parent().get()


    def gamestatus_as_dict(self):

        cvis = [card.get().as_cardstr() for card in self.cards_vis]
        cinv = [card.get().as_cardstr() for card in self.cards_inv]

        return {'actions': self.actions(),
                'your_cards_visible': cvis,
                'common_cards_visible': [],
                'players': self.game().players_as_dict()}


    def info_as_dict(self):

        cvis = [card.get().as_cardstr() for card in self.cards_vis]
        cinv = [card.get().as_cardstr() for card in self.cards_inv]
        cspl = [card.get().as_cardstr() for card in self.cards_spl]

        return {'name': self.name,
                'id': self.key.id(),
                'tokens': self.tokens,
                'avatar_url': self.a_url,
                'cards_visible': cvis,
                'cards_split': cspl,
                'cards_not_visible': cinv,
                'wager': self.wager,
                'status': self.sync}


    def hand_values(self, hand=None):

        result = {0}
        if not hand:
            hand = self.cards_vis
        cards = map(lambda card: card.get().map_value(),
                    self.cards_vis)

        logging.info('Calculating hand value for {}'\
                .format(self.name))

        for card_vals in cards:
            result = {int(a)+int(b)\
                    for a in card_vals\
                    for b in result}
            logging.info('--> vals {} ==> {}'.format(
                card_vals,
                result))

        return result


    def actions(self):

        logging.info('*** player => {}'.format(self.key.id()))
        if self.key.id() == 'dealer':
            ret = []

        game = self.game()

        if game.playing:

            # Actions for players
            if self.sync < 2:
                ret = ['hit',
                       'stand',
                       'doubledown']

                # Actions for the first round
                if self.sync == 0:
                    ret.append('surrender')

            # No actions if you're done playing this round
            else:
                ret = []

        # Nobody playing.  Let players join or skip the next round
        else:
            ret = ['join', 'skip']

        return ret


    def do_action(self, act, val):

        # Only let players do what we say they can
        if act not in self.actions():
            return

        # Dispatch action to corresponding function
        dispatch = getattr(self, '_{}'.format(act))
        dispatch(val)

        # Set proper sync value if the player did their
        # first action of the round
        if self.sync == 0 and self.game().playing:
            self.sync = 1
        self.put()

        # Trigger a game update
        self.game().selfupdate()


    def _hit(self, val=None):
        gkey = self.key.parent()
        deck = Deck.query(ancestor=gkey).get()
        card = deck.draw()

        # Add card to hand
        self.cards_vis.append(card.key)

        # Check for bust if the dealer is not playing
        if self.key.id() != 'dealer':
            hand_vals = self.hand_values(self.cards_vis)
            if all(h > 21 for h in hand_vals):
                self._stand()

        return card


    def _stand(self, val=None):
        self.sync = 2


    def _doubledown(self, val=None):

        # Double your wager
        self.wager += self.wager

        # Take a single card
        self._hit(val)

        # And stand
        self._stand(val)


    def _split(self, val=None):

        # Set up the two different decks
        self.cards_spl.append(self.cards_vis.pop())


    def _surrender(self, val=None):

        # Mark self as surrendered
        self.sync = 3


    def _join(self, val):

        if not val:
            return
        wager = int(val)

        # Submit bet
        self.wager = wager
        self.tokens -= wager

        # Set proper sync value
        self.sync = 0


    def _skip(self, val=None):

        # Don't bet anything, but say you're ready
        if self.wager is not None:
            self.tokens += self.wager
        self.wager = None
        self.sync = 0
