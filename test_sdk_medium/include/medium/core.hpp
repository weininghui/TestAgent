#pragma once

namespace medium {
namespace core {

class Engine {
public:
    virtual ~Engine() = default;
    virtual int run() const = 0;
    int version() const;
};

}  // namespace core
}  // namespace medium

#ifdef MEDIUM_NET
namespace medium {
namespace net {

int connect(const char* host, int port);

}  // namespace net
}  // namespace medium
#endif
