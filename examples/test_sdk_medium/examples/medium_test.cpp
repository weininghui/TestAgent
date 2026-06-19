#include <gtest/gtest.h>
#include "medium/core.hpp"

using medium::core::Engine;

class StubEngine : public Engine {
public:
    int run() const override { return 42; }
};

TEST(MediumTest, EngineVersion) {
    StubEngine engine;
    EXPECT_EQ(engine.version(), 1);
    EXPECT_EQ(engine.run(), 42);
}

#ifdef MEDIUM_NET
#include "medium/net.hpp"
TEST(MediumTest, NetConnect) {
    EXPECT_EQ(medium::net::connect("localhost", 8080), 0);
}
#endif
