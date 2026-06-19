#pragma once

namespace medium {
namespace net {

class Client {
public:
    virtual bool open(const char* url) = 0;
    void close();
};

}  // namespace net
}  // namespace medium
