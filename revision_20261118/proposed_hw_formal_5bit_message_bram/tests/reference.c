// Compile the untouched snapshotted decoder. Only MAX_ITER is made runtime-
// configurable for bounded RTL tests; at 200 it is the original loop bound.
#include "ldpc_config.h"
#include "ldpc.h"
static int reference_limit=200;
#undef MAX_ITER
#define MAX_ITER reference_limit
#include "ldpc.c"
#ifdef _WIN32
#define EXPORT __declspec(dllexport)
#else
#define EXPORT
#endif
EXPORT int reference_decode(int8_t *input,uint8_t *output,int limit) {
    reference_limit=limit<1?1:limit>200?200:limit;
    return ldpc_decode_nms(input,output);
}
EXPORT void reference_encode(uint8_t *message,uint8_t *codeword) {
    ldpc_encode(message,codeword);
}

// Explicit reduced-precision reference. int8_t is a storage container only;
// input, extrinsic and ordered posterior additions all saturate to +/-15.
static int clip5(int x) { return x>15?15:x< -15?-15:x; }
EXPORT int reference_decode5(int8_t *input,uint8_t *output,int limit) {
    int8_t channel[N],v[N],messages[M][MAX_ROW_DEGREE];
    memset(messages,0,sizeof(messages));
    for(int c=0;c<N;c++) channel[c]=v[c]=(int8_t)clip5(input[c]);
    limit=limit<1?1:limit>200?200:limit;
    for(int it=1;it<=limit;it++) {
        for(int r=0;r<M;r++) {
            int smallest=15,second=15,pos=-1,total=0;
            int ext[MAX_ROW_DEGREE];
            for(int k=0;k<H_row_degrees[r];k++) {
                ext[k]=clip5(v[H_row_indices[r][k]]-messages[r][k]);
                int a=ext[k]<0?-ext[k]:ext[k];
                total^=ext[k]<0;
                if(a<smallest){second=smallest;smallest=a;pos=k;}
                else if(a<second)second=a;
            }
            for(int k=0;k<H_row_degrees[r];k++) {
                int a=k==pos?second:smallest;
                a-=a>>2;
                messages[r][k]=(int8_t)((total^(ext[k]<0))?-a:a);
            }
        }
        memcpy(v,channel,sizeof(v));
        for(int r=0;r<M;r++)for(int k=0;k<H_row_degrees[r];k++) {
            int c=H_row_indices[r][k];
            v[c]=(int8_t)clip5(v[c]+messages[r][k]);
        }
        for(int c=0;c<N;c++)output[c]=v[c]<0;
        int failed=0;
        for(int r=0;r<M;r++) {
            int parity=0;
            for(int k=0;k<H_row_degrees[r];k++)parity^=output[H_row_indices[r][k]];
            if(parity){failed=1;break;}
        }
        if(!failed)return it;
    }
    return 0;
}
