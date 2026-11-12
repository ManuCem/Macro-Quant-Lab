// Compile: g++ option_pricer.cpp -o option_pricer
// Run:     ./option_pricer          (on Windows: option_pricer.exe)
//
// Black-Scholes price of a 30-day call and put on the S&P 500, and the call's delta.
// The same maths as option_pricer.py. Copy the 5 inputs from the web page, then compile and run again.

#include <iostream>  // lets us print to the screen with std::cout
#include <cmath>     // gives us std::log, std::sqrt, std::exp and std::erf

// ---- The 5 inputs: edit these by hand (the web page shows today's values) ----
double S = 7628.24;        // S&P 500 level today (Yahoo ^GSPC)
double K = 7630;           // strike: S rounded to the nearest 5
double r = 0.04125;        // interest rate: 13-week T-bill (Yahoo ^IRX) divided by 100
double sigma = 0.1748;     // volatility: VIX (Yahoo ^VIX) divided by 100
double T = 30.0 / 365.0;   // time to expiry in years: 30 days out of 365

// N(x): the share of the bell curve to the left of x, a probability between 0 and 1
double N(double x) {
    return 0.5 * (1.0 + std::erf(x / std::sqrt(2.0)));  // the standard formula, written with the error function erf
}

int main() {
    double volT = sigma * std::sqrt(T);                                   // the typical move over the option's life
    double d1 = (std::log(S / K) + (r + sigma * sigma / 2.0) * T) / volT; // first step of Black-Scholes
    double d2 = d1 - volT;                                                // second step: d1 minus one typical move
    double discount = std::exp(-r * T);                                   // what $1 paid at expiry is worth today

    double call = S * N(d1) - K * discount * N(d2);   // call price: right to BUY at K
    double put = K * discount * N(-d2) - S * N(-d1);  // put price: right to SELL at K
    double callDelta = N(d1);                         // call delta: price change per 1-point move of the index

    std::cout << std::fixed;      // print numbers with a fixed number of decimals
    std::cout.precision(4);       // 4 decimals, like the Python script

    std::cout << "Call price: " << call << "\n";       // e.g. Call price: 164.5856
    std::cout << "Put price:  " << put << "\n";        // e.g. Put price:  140.5206
    std::cout << "Call delta: " << callDelta << "\n";  // e.g. Call delta: 0.5351

    return 0;                     // 0 tells the computer the program ended without errors
}
