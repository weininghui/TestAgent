#include "medium/core.hpp"

namespace medium {
namespace core {

int Engine::version() const {
    return 1;
}

}  // namespace core
}  // namespace medium

#ifdef MEDIUM_NET
#include "medium/net.hpp"

namespace medium {
namespace net {

int connect(const char* host, int port) {
    (void)host;
    (void)port;
    return 0;
}

void Client::close() {}

}  // namespace net
}  // namespace medium
#endif
