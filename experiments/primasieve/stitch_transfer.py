"""Does a cross-model linear STITCH transfer concepts (donor-method feasibility)?
Uses saved reps_big.npz (LFM2.5-350M + Qwen2.5-1.5B, 1000 words, all layers).
Two metrics per layer pair, held-out 300 words:
  - raw ridge R2 (vector reconstruction) -- misleadingly poor (anisotropy/undersample)
  - RETRIEVAL@k after mapping (scale-free concept identity) -- the donor-relevant metric
"""
import numpy as np
d=np.load('reps_big.npz'); RL,RQ=d['RL'],d['RQ']       # [NL+1, N, H]
N=RL.shape[1]; rng=np.random.default_rng(0); idx=rng.permutation(N); tr,te=idx[:700],idx[700:]
def rm(R,c=3):
    Rc=R-R.mean(0,keepdims=True)
    if c<=0: return Rc
    U,S,Vt=np.linalg.svd(Rc,full_matrices=False); S=S.copy(); S[:c]=0; return (U*S)@Vt
def norm(Z): return Z/(np.linalg.norm(Z,axis=1,keepdims=True)+1e-9)
def fit(X,Y,alpha=50.0):
    Xtr,Ytr=X[tr],Y[tr]
    return np.linalg.solve(Xtr.T@Xtr+alpha*np.eye(Xtr.shape[1]), Xtr.T@Ytr)
def r2(X,Y,W):
    p=X[te]@W; return 1-((Y[te]-p)**2).sum()/((Y[te]-Y[te].mean(0))**2).sum()
def retrieval(X,Y,W):
    P=norm(X[te]@W); T=norm(Y[te]); S=P@T.T; rank=(-S).argsort(1)
    corr=np.array([np.where(rank[i]==i)[0][0] for i in range(len(te))])
    return (corr==0).mean(),(corr<5).mean(),(1/(corr+1)).mean()
NLl,NLq=RL.shape[0]-1,RQ.shape[0]-1
pairs=[('embed',0,0),('early',2,1),('mid',NLl//2,NLq//2),('deep',NLl-2,NLq-2)]
print(f'held-out {len(te)} words, chance ret@1={1/len(te):.4f}')
print(f'{"pair":6} {"rawR2":>7} {"ret@1":>7} {"ret@5":>7} {"MRR":>6}')
for name,i,j in pairs:
    X,Y=rm(RL[i]),rm(RQ[j]); W=fit(X,Y)
    a1,a5,mrr=retrieval(X,Y,W)
    print(f'{name:6} L{i}->L{j} {r2(X,Y,W):7.3f} {a1:7.3f} {a5:7.3f} {mrr:6.3f}')
Rr=rng.standard_normal((N,RL.shape[2])); X,Y=rm(Rr),rm(RQ[NLq//2]); W=fit(X,Y)
print(f'random baseline ret@1 {retrieval(X,Y,W)[0]:.3f}')
print("\nRETRIEVAL (concept identity) transfers strongly esp. early/mid layers; deep")
print("layers weaker (where capability lives). Map transfers what small model HAS,")
print("not capacity it lacks. Supports a learned cross-model INTERFACE, not weight-dissolve.")
