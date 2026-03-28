class Treenode:
    def __init__(self):
        self.data=0
        self.left=None
        self.right=None
class Binarytree:
    def insert(self,t,d):
        if t==None:
            newnode=Treenode()
            newnode.data=d
            newnode.left=None
            newnode.right=None
            return newnode
        elif t.data>d:
            t.left=self.insert(t.left,d)
        elif t.data<d:
            t.right=self.insert(t.left,d)
        else

