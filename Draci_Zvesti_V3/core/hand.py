class Hand:
    cards=None
    def __init__(self) -> None:
        self.cards = []
    def sort(self):
        self.cards.sort(key=lambda x: x.name)
    def cards_num_arr(self):
        ret = []
        for card in self.cards:
            ret.append( card.name)
        while len(ret) < 12:
            ret.append(0)
        return ret