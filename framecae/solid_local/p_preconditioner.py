"""Auxiliary linear space for the quadratic system; K and the PDE stay intact."""
import numpy as np
from scipy.sparse import coo_matrix,diags,eye,kron
import pyamg
from pyamg.relaxation.smoothing import setup_block_gauss_seidel


def build(A,points,cells,scale,candidates,free_nodes=None):
    """Symmetric V cycle: Tet10 smoothing -> corner space -> algebraic AMG.

    Corner interpolation is used ONLY inside the preconditioner. The outer
    CG operator, curved geometry, displacement order and stress recovery all
    remain the original Tet10 system.
    """
    nn=len(points);free_nodes=np.arange(nn) if free_nodes is None else np.asarray(free_nodes)
    corners=np.unique(cells[:,:4]);mid=cells[:,4:].ravel();edges=((0,1),(1,2),(0,2),(0,3),(1,3),(2,3))
    endpoints=np.stack([cells[:,[a,b]] for a,b in edges],axis=1).reshape(-1,2)
    mid,first=np.unique(mid,return_index=True);endpoints=endpoints[first]
    if np.intersect1d(mid,corners).size:raise ValueError('Corner and midside roles overlap')
    rows=np.r_[corners,np.repeat(mid,2)];cols=np.r_[np.arange(len(corners)),np.searchsorted(corners,endpoints).ravel()]
    values=np.r_[np.ones(len(corners)),np.full(len(mid)*2,.5)]
    nodeP=coo_matrix((values,(rows,cols)),shape=(nn,len(corners))).tocsr()
    lookup=np.full(nn,-1,dtype=np.int64);lookup[free_nodes]=np.arange(len(free_nodes));keep=np.flatnonzero(lookup[corners]>=0)
    nodeP=nodeP[free_nodes][:,keep];corner_nodes=corners[keep]
    P=(diags(1/scale)@kron(nodeP,eye(3),format='csr')).tocsr()
    coarse=(P.T@(A@P)).tocsr();coarse=(coarse+coarse.T)*.5
    cs=1/np.sqrt(coarse.diagonal());P=(P@diags(cs)).tocsr();coarse=(diags(cs)@coarse@diags(cs)).tobsr(blocksize=(3,3))
    corner_dofs=(lookup[corner_nodes,None]*3+np.arange(3)).ravel()
    B=candidates[corner_dofs]*scale[corner_dofs,None]/cs[:,None]
    B/=np.maximum(np.linalg.norm(B,axis=0),1e-30)
    coarse_ml=pyamg.smoothed_aggregation_solver(coarse,B=B,symmetry='symmetric',max_levels=12,max_coarse=max(5,240//B.shape[1]),coarse_solver='pinv',presmoother=('block_gauss_seidel',{'sweep':'symmetric'}),postsmoother=('block_gauss_seidel',{'sweep':'symmetric'}))
    fine=pyamg.multilevel.MultilevelSolver.Level();fine.A=A;fine.P=P;fine.R=P.T.tocsr();fine.B=candidates
    fine.presmoother=setup_block_gauss_seidel(fine,sweep='symmetric');fine.postsmoother=setup_block_gauss_seidel(fine,sweep='symmetric')
    ml=pyamg.multilevel.MultilevelSolver([fine,*coarse_ml.levels],coarse_solver='pinv');ml.symmetric_smoothing=True
    print('TET10_AUXILIARY_SPACE',A.shape[0],'->',coarse.shape[0],'DOFS; levels',len(ml.levels),flush=True)
    return ml
