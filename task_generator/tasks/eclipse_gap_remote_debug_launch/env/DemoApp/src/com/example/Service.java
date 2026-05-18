package com.example;

public class Service {
	private int counter = 0;

	public void increment() {
		counter = counter + 1;
		if (counter > 10) {
			System.out.println("threshold crossed");
		}
		System.out.println("counter = " + counter);
	}

	public int getCounter() {
		return counter;
	}
}
