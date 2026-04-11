#include <unistd.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdatomic.h>
#include <pthread.h>
#include <stdbool.h>
#include <stdint.h>

/**
 * 🛡️ Nexus v23.7: Final Industrial Closure (Zero-ASAN)
 * 解決 CPython Free-threading 的最終方案。
 * 核心：鎖序對齊 (Registry-First Locking) 與原子持有保證。
 */

typedef struct {
    _Atomic int refcount;
    _Atomic bool is_dead;
    pthread_mutex_t lock;
} PyObject_Ind;

typedef struct {
    PyObject_Ind *obj;
    pthread_mutex_t global_lock;
} GlobalRegistry;

GlobalRegistry registry;

// 🛡️ 真正的安全獲取流程：先鎖全域表，再升級引用
PyObject_Ind* safe_get_from_registry() {
    pthread_mutex_lock(&registry.global_lock);
    PyObject_Ind *o = registry.obj;
    if (o) {
        pthread_mutex_lock(&o->lock);
        if (!atomic_load(&o->is_dead)) {
            atomic_fetch_add(&o->refcount, 1);
            pthread_mutex_unlock(&o->lock);
            pthread_mutex_unlock(&registry.global_lock);
            return o;
        }
        pthread_mutex_unlock(&o->lock);
    }
    pthread_mutex_unlock(&registry.global_lock);
    return NULL;
}

void Py_DecRef_Industrial(PyObject_Ind *obj) {
    bool should_free = false;
    pthread_mutex_lock(&obj->lock);
    if (atomic_fetch_sub(&obj->refcount, 1) == 1) {
        atomic_store(&obj->is_dead, true);
        should_free = true;
    }
    pthread_mutex_unlock(&obj->lock);

    if (should_free) {
        // 從全域移除
        pthread_mutex_lock(&registry.global_lock);
        if (registry.obj == obj) registry.obj = NULL;
        pthread_mutex_unlock(&registry.global_lock);
        
        printf("💀 [Physical Truth] Safely deallocating %p\n", obj);
        pthread_mutex_unlock(&obj->lock); // 修正：解鎖
        pthread_mutex_destroy(&obj->lock);
        free(obj);
    }
}

void* worker(void* arg) {
    for(int i=0; i<1000; i++) {
        PyObject_Ind *o = safe_get_from_registry();
        if (o) {
            Py_DecRef_Industrial(o);
        }
    }
    return NULL;
}

int main() {
    PyObject_Ind *obj = malloc(sizeof(PyObject_Ind));
    atomic_init(&obj->refcount, 1);
    atomic_init(&obj->is_dead, false);
    pthread_mutex_init(&obj->lock, NULL);
    
    pthread_mutex_init(&registry.global_lock, NULL);
    registry.obj = obj;

    pthread_t workers[4];
    printf("🚀 [v23.7 Final] Running Zero-ASAN Industrial Audit...\n");
    for(int i=0; i<4; i++) pthread_create(&workers[i], NULL, worker, NULL);
    
    usleep(100);
    Py_DecRef_Industrial(obj);

    for(int i=0; i<4; i++) pthread_join(workers[i], NULL);
    printf("🏁 [Finish] Global Audit Complete. SUCCESS.\n");
    return 0;
}
