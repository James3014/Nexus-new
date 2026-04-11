#include <unistd.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdatomic.h>
#include <pthread.h>
#include <stdbool.h>
#include <stdint.h>

typedef struct {
    _Atomic int refcount;
    _Atomic bool is_dead;
    pthread_mutex_t lock;
} PyObject_Ind;

typedef struct {
    PyObject_Ind *slots[1];
    pthread_mutex_t dict_lock;
} MockWeakDict;

MockWeakDict global_dict;

void Py_DecRef_Industrial(PyObject_Ind *obj) {
    bool should_free = false;
    pthread_mutex_lock(&obj->lock);
    if (atomic_fetch_sub(&obj->refcount, 1) == 1) {
        atomic_store(&obj->is_dead, true);
        should_free = true;
    }
    pthread_mutex_unlock(&obj->lock);

    if (should_free) {
        pthread_mutex_lock(&global_dict.dict_lock);
        if (global_dict.slots[0] == obj) global_dict.slots[0] = NULL;
        pthread_mutex_unlock(&global_dict.dict_lock);
        pthread_mutex_destroy(&obj->lock);
        free(obj);
    }
}

void* worker(void* arg) {
    int iterations = *(int*)arg;
    for(int i=0; i<iterations; i++) {
        PyObject_Ind *target = NULL;
        pthread_mutex_lock(&global_dict.dict_lock);
        target = global_dict.slots[0];
        if (target) {
            pthread_mutex_lock(&target->lock);
            if (!atomic_load(&target->is_dead)) {
                atomic_fetch_add(&target->refcount, 1);
            } else {
                target = NULL;
            }
            if (target) pthread_mutex_unlock(&target->lock);
        }
        pthread_mutex_unlock(&global_dict.dict_lock);
        if (target) Py_DecRef_Industrial(target);
    }
    return NULL;
}

int main(int argc, char** argv) {
    int iterations = (argc > 1) ? atoi(argv[1]) : 500;
    PyObject_Ind *obj = malloc(sizeof(PyObject_Ind));
    atomic_init(&obj->refcount, 1);
    atomic_init(&obj->is_dead, false);
    pthread_mutex_init(&obj->lock, NULL);
    pthread_mutex_init(&global_dict.dict_lock, NULL);
    global_dict.slots[0] = obj;

    pthread_t workers[4];
    for(int i=0; i<4; i++) pthread_create(&workers[i], NULL, worker, &iterations);
    Py_DecRef_Industrial(obj);
    for(int i=0; i<4; i++) pthread_join(workers[i], NULL);
    printf("🏁 Audit Complete. Iterations per worker: %d\n", iterations);
    return 0;
}
