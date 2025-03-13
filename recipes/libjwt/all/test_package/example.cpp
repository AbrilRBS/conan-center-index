#include "jwt.h"

int main() {

    jwt_builder_t* builder = jwt_builder_new();
    jwt_builder_free(builder);
    return 0;
}
