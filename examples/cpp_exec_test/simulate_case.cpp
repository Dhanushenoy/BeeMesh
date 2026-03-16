#include <cmath>
#include <cstdlib>
#include <iostream>

int main(int argc, char** argv)
{
    if (argc < 2) {
        std::cerr << "Usage: simulate_case <n>" << std::endl;
        return 1;
    }

    int n = std::atoi(argv[1]);
    double s = 0.0;
    for (int i = 0; i < 20000000; ++i) {
        double x = std::sin(i * 0.00001 * n);
        s += x * x;
    }

    std::cout << s << std::endl;
    return 0;
}
