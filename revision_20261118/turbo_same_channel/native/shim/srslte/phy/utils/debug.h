#ifndef TURBO_LOCAL_DEBUG_H
#define TURBO_LOCAL_DEBUG_H
#include <stdio.h>
#define ERROR(...) do { fprintf(stderr, __VA_ARGS__); fputc('\n', stderr); } while (0)
#endif
