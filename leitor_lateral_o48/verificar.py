import os,json,hashlib,sys
A=os.path.dirname(os.path.abspath(__file__));M=json.load(open(os.path.join(A,"MANIFESTO_O48.json")))
bad=[a for a,h in M.items() if hashlib.sha256(open(os.path.join(A,a),"rb").read()).hexdigest()!=h]
print("VERIFICADO" if not bad else bad,len(M));sys.exit(1 if bad else 0)
