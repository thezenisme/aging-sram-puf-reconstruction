/* SPDX-License-Identifier: AGPL-3.0-or-later
 * The original source is included unchanged, solely to expose its static
 * constituent MAP routine for independent exhaustive-path validation.
 */
#include "turbo_native.h"
#include <math.h>
#include "../vendor/srslte_17_12/turbodecoder_gen.c"

int turbo_component_map(const float *systematic, const float *parity,
                        float *posterior, int length)
{
  if (!systematic || !parity || !posterior || length < 1 || length > 6144)
    return -1;
  float *s = malloc((length + 3) * sizeof(float));
  float *p = malloc((length + 3) * sizeof(float));
  srslte_map_gen_vl_t h;
  if (!s || !p) { free(s); free(p); return -2; }
  for (int i = 0; i < length + 3; ++i) {
    if (!isfinite(systematic[i]) || !isfinite(parity[i])) {
      free(s); free(p); return -1;
    }
    s[i] = -systematic[i];
    p[i] = -parity[i];
  }
  if (map_gen_init(&h, length)) { free(s); free(p); return -2; }
  map_gen_dec(&h, s, p, posterior, length);
  for (int i = 0; i < length; ++i) posterior[i] = -posterior[i];
  map_gen_free(&h);
  free(s);
  free(p);
  return 0;
}
