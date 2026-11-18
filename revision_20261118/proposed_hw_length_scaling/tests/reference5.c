// Independent software execution over full H rows, with five-bit saturation.
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#define EXPORT __declspec(dllexport)
#else
#define EXPORT
#endif
static int clip(int x) { return x>15?15:x< -15?-15:x; }
EXPORT int decode5(int n,int m,const uint32_t *offsets,const uint16_t *cols,
                   const int8_t *input,uint8_t *output,int limit) {
    int edges=offsets[m];
    int8_t *v=malloc(n), *channel=malloc(n), *messages=calloc(edges,1);
    if(!v || !channel || !messages) abort();
    for(int c=0;c<n;c++) channel[c]=v[c]=clip(input[c]);
    limit=limit<1?1:limit>200?200:limit;
    int result=0;
    for(int it=1;it<=limit;it++) {
        for(int r=0;r<m;r++) {
            int smallest=15,second=15,pos=-1,total=0;
            int ext[64];
            int a=offsets[r],b=offsets[r+1];
            for(int e=a;e<b;e++) {
                int x=ext[e-a]=clip(v[cols[e]]-messages[e]);
                int mag=x<0?-x:x; total^=x<0;
                if(mag<smallest){second=smallest;smallest=mag;pos=e;}
                else if(mag<second)second=mag;
            }
            for(int e=a;e<b;e++) {
                int mag=e==pos?second:smallest; mag-=mag>>2;
                messages[e]=(total^(ext[e-a]<0))?-mag:mag;
            }
        }
        memcpy(v,channel,n);
        for(int e=0;e<edges;e++) v[cols[e]]=clip(v[cols[e]]+messages[e]);
        for(int c=0;c<n;c++) output[c]=v[c]<0;
        int fail=0;
        for(int r=0;r<m;r++) {
            int parity=0;
            for(int e=offsets[r];e<offsets[r+1];e++) parity^=output[cols[e]];
            if(parity){fail=1;break;}
        }
        if(!fail){result=it;break;}
    }
    free(v);free(channel);free(messages);
    return result;
}
