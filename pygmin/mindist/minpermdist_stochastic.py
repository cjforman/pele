import distpot
import numpy as np
import pygmin.utils.rotations as rot
from pygmin.optimize.quench import quench
from  pygmin import basinhopping
import pygmin.storage.savenlowest as storage
from mindistutils import CoMToOrigin, aa2xyz, alignRotation, findBestPermutation

__all__ = ["minPermDistStochastic"]

def minPermDistStochastic(X1, X2, niter = 100, permlist = None, verbose = False):
    """
    Minimize the distance between two clusters.  
    
    Parameters
    ----------
    X1, X2 : 
        the structures to align.  X2 will be aligned with X1, both
        the center of masses will be shifted to the origin
    niter : int
        the number of basinhopping iterations to perform
    permlist : a list of lists of atoms 
        A list of lists of atoms which are interchangable.
        e.g. if all the atoms are interchangable
        
            permlist = [range(natoms)]
        
        For a 50/50 binary mixture, 
        
            permlist = [range(1,natoms/2), range(natoms/2,natoms)]
    verbose : 
        whether to print status information

    Notes
    -----

    The following symmetries will be accounted for
    
        Translational symmetry

        Global rotational symmetry

        Permutational symmetry

    
    
    This method uses basin hopping to find the rotation of X2 which best
    optimizes the overlap (an effective energy) between X1 and X2.  The overlap
    is defined to be permutation independent.

    Once the rotation is optimized, the correct permutation can be determined
    deterministically using the Hungarian algorithm.
    
    """
    nsites = len(X1)/3
    if permlist is None:
        permlist = [range(nsites)]

    ###############################################
    # move the centers of mass to the origin
    ###############################################
    X1 = CoMToOrigin(X1)
    X2 = CoMToOrigin(X2)
    X2in = np.copy(X2) #I wish i could declare this constant

    ###############################################
    # set initial conditions
    ###############################################
    aamin = np.array([0.,0.,0.])

    ######################################
    # set up potential
    ######################################
    pot = distpot.MinPermDistPotential( X1, X2, 0.2, permlist )
    if verbose:
        #print some stuff. not necessary
        Emin = pot.getEnergy(aamin)
        dist, X11, X22 = findBestPermutation(X1, aa2xyz(X2in, aamin), permlist )
        print "initial energy", Emin, "dist", dist
    saveit = storage.SaveN( 20 )
    takestep = distpot.RandomRotationTakeStep()
    bh = basinhopping.BasinHopping( aamin, pot, takestep, storage=saveit.insert, outstream = None)


    Eminglobal = pot.globalEnergyMin() #condition for determining isomer
    if verbose: print "global Emin", Eminglobal

    ##########################################################################
    # run basin hopping for ninter steps or until the global minimum is found
    # (i.e. determine they are isomers)
    ##########################################################################
    if verbose: print "using basin hopping to optimize rotations + permutations"
    for i in range(niter):
        bh.run(1)
        Emin = saveit.data[0].energy
        if abs(Emin-Eminglobal) < 1e-6:
            if verbose: print "isomer found"
            break

    """
    Lower energies generally mean smaller distances, but it's not guaranteed.
    Check a number of the lowest energy structures. To ensure get the correct
    minimum distance structure.
    """
    if verbose: print "lowest structures found"
    aamin = saveit.data[0].coords
    dmin, X11, X22 = findBestPermutation(X1, aa2xyz(X2in, aamin), permlist )
    for minimum in saveit.data:
        dist, X11, X22 = findBestPermutation(X1, aa2xyz(X2in, minimum.coords), permlist )
        if verbose: print "E %11.5g dist %11.5g" % (minimum.energy, dist)
        if dist < dmin:
            dmin = dist
            aamin = minimum.coords

    ###################################################################
    #we've optimized the rotation in a permutation independent manner
    #now optimize the permutation
    ###################################################################
    dmin, X1, X2min = findBestPermutation(X1, aa2xyz(X2in, aamin), permlist )

    ###################################################################
    # permutations are set, do one final mindist improve accuracy
    #of rotation optimization
    ###################################################################
    dmin, X2min = alignRotation( X1, X2min )

    return dmin, X1, X2min





import unittest
from testmindist import TestMinDist
class TestMinPermDistStochastic_BLJ(TestMinDist):
    def setUp(self):
        from pygmin.potentials.ljpshift import LJpshift as BLJ
        from pygmin import defaults
        
        self.natoms = 25
        self.ntypeA = int(self.natoms * .8)
        self.pot = BLJ(self.natoms, self.ntypeA)
        self.permlist = [range(self.ntypeA), range(self.ntypeA, self.natoms)]
        
        self.X1 = np.random.uniform(-1,1,[self.natoms*3])*(float(self.natoms))**(1./3)/2
        
        #run a quench so the structure is not crazy
        ret = defaults.quenchRoutine(self.X1, self.pot.getEnergyGradient, **defaults.quenchParams)
        self.X1 = ret[0]
        

    def testBLJ(self):
        X1 = np.copy(self.X1)
        X2 = np.random.uniform(-1,1,[self.natoms*3])*(float(self.natoms))**(1./3)/2
        
        #run a quench so the structure is not crazy
        ret = quench(X2, self.pot.getEnergyGradient)
        X2 = ret[0]

        self.runtest(X1, X2, minPermDistStochastic)


    def testBLJ_isomer(self):
        """
        test with BLJ potential.  We have two classes of permutable atoms  
        
        test case where X2 is an isomer of X1.
        """
        X1i = np.copy(self.X1)
        X1 = np.copy(self.X1)        
        X2 = np.copy(X1)
        
        #rotate X2 randomly
        aa = rot.random_aa()
        rot_mx = rot.aa2mx( aa )
        for j in range(self.natoms):
            i = 3*j
            X2[i:i+3] = np.dot( rot_mx, X1[i:i+3] )
        
        #permute X2
        import random, mindistutils, copy
        for atomlist in self.permlist:
            perm = copy.copy(atomlist)
            random.shuffle( perm )
            X2 = mindistutils.permuteArray( X2, perm)

        X2i = np.copy(X2)
        
        #distreturned, X1, X2 = self.runtest(X1, X2)
        distreturned, X1, X2 = self.runtest(X1, X2, minPermDistStochastic)

        
        #it's an isomer, so the distance should be zero
        self.assertTrue( abs(distreturned) < 1e-14, "didn't find isomer: dist = %g" % (distreturned) )


def test(X1, X2, lj, atomtypes=["LA"], permlist = None, fname = "lj.xyz"):
    import copy
    natoms = len(X1) / 3
    if permlist == None:
        permlist = [range(natoms)]
    
    X1i = copy.copy(X1)
    X2i = copy.copy(X2)
    
    printlist = []
    printlist.append((X2.copy(), "X2 initial"))
    printlist.append((X1.copy(), "X1 initial"))


    distinit = np.linalg.norm(X1-X2)
    print "distinit", distinit

    (dist, X1, X2) = minPermDistStochastic(X1,X2, permlist=permlist)
    distfinal = np.linalg.norm(X1-X2)
    print "dist returned    ", dist
    print "dist from coords ", distfinal
    print "initial energies (post quench)", lj.getEnergy(X1i), lj.getEnergy(X2i)
    print "final energies                ", lj.getEnergy(X1), lj.getEnergy(X2)

    printlist.append((X1.copy(), "X1 final"))
    printlist.append((X2.copy(), "X2 final"))


    import pygmin.printing.print_atoms_xyz as printxyz
    with open(fname, "w") as fout:
        for xyz, line2 in printlist:
            printxyz.printAtomsXYZ(fout, xyz, line2=line2 +" "+ str(lj.getEnergy(xyz)))

    

def test_binary_LJ(natoms = 12):
    printlist = []
    
    ntypea = int(natoms*.8)
    from pygmin.potentials.ljpshift import LJpshift
    lj = LJpshift(natoms, ntypea)
    permlist = [range(ntypea), range(ntypea, natoms)]

    X1 = np.random.uniform(-1,1,[natoms*3])*(float(natoms))**(1./3)/2
    printlist.append( (X1.copy(), "very first"))
    #quench X1
    ret = quench( X1, lj.getEnergyGradient)
    X1 = ret[0]
    printlist.append((X1.copy(), "after quench"))

    X2 = np.random.uniform(-1,1,[natoms*3])*(float(natoms))**(1./3)
    #make X2 a rotation of X1
    print "testing with", natoms, "atoms,", ntypea, "type A atoms, with X2 a rotated and permuted isomer of X1"
    aa = rot.random_aa()
    rot_mx = rot.aa2mx( aa )
    for j in range(natoms):
        i = 3*j
        X2[i:i+3] = np.dot( rot_mx, X1[i:i+3] )
    printlist.append((X2.copy(), "x2 after rotation"))
    

    

    import random, mindistutils, copy
    for atomlist in permlist:
        perm = copy.copy(atomlist)
        random.shuffle( perm )
        print perm
        X2 = mindistutils.permuteArray( X2, perm)
    printlist.append((X2.copy(), "x2 after permutation"))


    #X1 = np.array( [ 0., 0., 0., 1., 0., 0., 0., 0., 1.,] )
    #X2 = np.array( [ 0., 0., 0., 1., 0., 0., 0., 1., 0.,] )
    X1i = copy.copy(X1)
    X2i = copy.copy(X2)
    
    atomtypes = ["N" for i in range(ntypea)]
    for i in range(natoms-ntypea):
        atomtypes.append("O")
    
    print "******************************"
    print "testing binary LJ  ISOMER"
    print "******************************"
    test(X1, X2, lj, atomtypes=atomtypes, permlist = permlist)
    
    print "******************************"
    print "testing binary LJ  non isomer"
    print "******************************"
    X2 = np.random.uniform(-1,1,[natoms*3])*(float(natoms))**(1./3)
    ret = quench( X2, lj.getEnergyGradient)
    X2 = ret[0]
    test(X1, X2, lj, atomtypes=atomtypes, permlist=permlist)

    
        
        
def test_LJ(natoms = 12):
    from pygmin.potentials.lj import LJ
    lj = LJ()
    X1 = np.random.uniform(-1,1,[natoms*3])*(float(natoms))**(1./3)
    #quench X1
    ret = quench( X1, lj.getEnergyGradient)
    X1 = ret[0]
    X2 = np.random.uniform(-1,1,[natoms*3])*(float(natoms))**(1./3)
    #make X2 a rotation of X1
    print "testing with", natoms, "atoms, with X2 a rotated and permuted isomer of X1"
    aa = rot.random_aa()
    rot_mx = rot.aa2mx( aa )
    for j in range(natoms):
        i = 3*j
        X2[i:i+3] = np.dot( rot_mx, X1[i:i+3] )
    import random, mindistutils
    perm = range(natoms)
    random.shuffle( perm )
    print perm
    X2 = mindistutils.permuteArray( X2, perm)

    #X1 = np.array( [ 0., 0., 0., 1., 0., 0., 0., 0., 1.,] )
    #X2 = np.array( [ 0., 0., 0., 1., 0., 0., 0., 1., 0.,] )
    import copy
    X1i = copy.copy(X1)
    X2i = copy.copy(X2)
    
    print "******************************"
    print "testing normal LJ  ISOMER"
    print "******************************"
    test(X1, X2, lj)
    
    print "******************************"
    print "testing normal LJ  non isomer"
    print "******************************"
    X2 = np.random.uniform(-1,1,[natoms*3])*(float(natoms))**(1./3)
    ret = quench( X2, lj.getEnergyGradient)
    X2 = ret[0]
    test(X1, X2, lj)
    

    distinit = np.linalg.norm(X1-X2)
    print "distinit", distinit



if __name__ == "__main__":
    print "******************************"
    print "testing normal LJ"
    print "******************************"
    test_LJ(12)
    print ""
    print ""
    print "************************************"
    print "testing binary LJ with permute lists"
    print "************************************"
    test_binary_LJ(12)
    
    unittest.main()
    
    
