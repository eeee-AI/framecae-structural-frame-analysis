"""Curved isoparametric Tet10: Ke=integral B.T D B dV; sigma=D B u.

Canonical node order follows Abaqus C3D10/VTK: corners 0..3, then
edges 01,12,02,03,13,23. Engineering strains: xx,yy,zz,xy,xz,yz.
The reference quadrature is supplied by BSD-licensed scikit-fem.
Shape-function formulas are the standard barycentric quadratic simplex basis.
"""
import numpy as np
from scipy.sparse import coo_matrix,bsr_matrix
from skfem.quadrature import get_quadrature_tet

EDGES=((0,1),(1,2),(0,2),(0,3),(1,3),(2,3))
REFERENCE_NODES=np.array([[0,0,0],[1,0,0],[0,1,0],[0,0,1],[.5,0,0],[.5,.5,0],[0,.5,0],[0,0,.5],[.5,0,.5],[0,.5,.5]])


def shape(xi):
    xi=np.atleast_2d(xi);l=np.c_[1-xi.sum(axis=1),xi]
    dl=np.array([[-1.,-1,-1],[1,0,0],[0,1,0],[0,0,1]])
    n=np.empty((len(xi),10));g=np.empty((len(xi),10,3))
    n[:,:4]=l*(2*l-1);g[:,:4]=(4*l-1)[:,:,None]*dl
    for k,(a,b) in enumerate(EDGES,4):n[:,k]=4*l[:,a]*l[:,b];g[:,k]=4*(l[:,b,None]*dl[a]+l[:,a,None]*dl[b])
    return n,g


def constitutive(E,nu):
    if not np.isfinite(E) or E<=0 or not np.isfinite(nu) or not -1<nu<.5:
        raise ValueError('Stable isotropic elasticity requires E>0 and -1<nu<0.5')
    lam=E*nu/((1+nu)*(1-2*nu));mu=E/(2*(1+nu));D=np.zeros((6,6))
    D[:3,:3]=lam;D[np.arange(3),np.arange(3)]+=2*mu;D[3:,3:]=mu*np.eye(3)
    return D


def gradients(coordinates,xi):
    _,ref=shape(xi);J=np.einsum('eni,qnj->eqij',coordinates,ref,optimize=True)
    det=np.linalg.det(J)
    if np.any(det<=0):raise ValueError('Non-positive isoparametric Tet10 Jacobian')
    g=np.einsum('qnj,eqji->eqni',ref,np.linalg.inv(J),optimize=True)
    return g,det


def bmatrix(g):
    B=np.zeros((*g.shape[:2],6,30));dx,dy,dz=g[...,0],g[...,1],g[...,2]
    B[:,:,0,0::3]=dx;B[:,:,1,1::3]=dy;B[:,:,2,2::3]=dz
    B[:,:,3,0::3]=dy;B[:,:,3,1::3]=dx
    B[:,:,4,0::3]=dz;B[:,:,4,2::3]=dx
    B[:,:,5,1::3]=dz;B[:,:,5,2::3]=dy
    return B


def stiffness(coordinates,D,order=5):
    xi,w=get_quadrature_tet(order);g,det=gradients(coordinates,xi.T);B=bmatrix(g)
    DB=np.einsum('ij,eqja->eqia',D,B,optimize=True)
    return np.einsum('eqia,eqib,eq->eab',B,DB,det*w,optimize=True),det*w


def assemble(points,cells,D,progress=None,chunk=384):
    ne=len(cells);nn=len(points)
    # Three displacement components share a dense 3x3 block. Build the node
    # adjacency once rather than retaining 900 scalar COO entries per element.
    rows=np.repeat(cells,10,axis=1).ravel();cols=np.tile(cells,(1,10)).ravel()
    graph=coo_matrix((np.ones(len(rows),dtype=bool),(rows,cols)),shape=(nn,nn)).tocsr()
    del rows,cols
    keys=np.repeat(np.arange(nn,dtype=np.int64),np.diff(graph.indptr))*nn+graph.indices
    data=np.zeros((len(keys),3,3));volume=np.empty(ne)
    for start in range(0,ne,chunk):
        end=min(start+chunk,ne);k,w=stiffness(points[cells[start:end]],D)
        conn=cells[start:end].astype(np.int64)
        positions=np.searchsorted(keys,(conn[:,:,None]*nn+conn[:,None,:]).ravel())
        blocks=k.reshape(end-start,10,3,10,3).transpose(0,1,3,2,4).reshape(-1,3,3)
        np.add.at(data,positions,blocks);volume[start:end]=w.sum(axis=1)
        if progress and (start==0 or end==ne or start%(chunk*20)==0):progress(end,ne)
    K=bsr_matrix((data,graph.indices,graph.indptr),shape=(nn*3,nn*3))
    return K,volume


def free_block_matrix(K,free_nodes):
    nn=K.shape[0]//3;mapping=np.full(nn,-1,dtype=np.int32);mapping[free_nodes]=np.arange(len(free_nodes),dtype=np.int32)
    rows=np.repeat(np.arange(nn,dtype=np.int32),np.diff(K.indptr))
    keep=(mapping[rows]>=0)&(mapping[K.indices]>=0)
    counts=np.bincount(mapping[rows[keep]],minlength=len(free_nodes))
    ptr=np.r_[0,np.cumsum(counts)].astype(np.int32)
    return bsr_matrix((K.data[keep],mapping[K.indices[keep]],ptr),shape=(len(free_nodes)*3,)*2)


def evaluate_stress(coordinates,displacement,D,xi):
    g,_=gradients(coordinates,xi);u=np.asarray(displacement).reshape(len(coordinates),10,3)
    H=np.einsum('eni,eqnj->eqij',u,g,optimize=True)
    eps=np.stack((H[:,:,0,0],H[:,:,1,1],H[:,:,2,2],H[:,:,0,1]+H[:,:,1,0],H[:,:,0,2]+H[:,:,2,0],H[:,:,1,2]+H[:,:,2,1]),axis=-1)
    return np.einsum('ij,eqj->eqi',D,eps,optimize=True)


def body_force(points,cells,force_per_volume,chunk=1024):
    """Consistent constant volumetric loading, including quadratic corner signs."""
    vector=np.asarray(force_per_volume,dtype=float)
    loads=np.zeros_like(points,dtype=float)
    if not np.any(vector):return loads
    xi,w=get_quadrature_tet(5);N,_=shape(xi.T)
    for start in range(0,len(cells),chunk):
        conn=cells[start:start+chunk]
        _,det=gradients(points[conn],xi.T)
        weights=np.einsum('qn,eq,q->en',N,det,w)
        for j in range(10):np.add.at(loads,conn[:,j],weights[:,j,None]*vector)
    return loads


def mises(s):
    a,b,c,d,e,f=np.moveaxis(np.asarray(s),-1,0)
    return np.sqrt(.5*((a-b)**2+(b-c)**2+(c-a)**2)+3*(d*d+e*e+f*f))
